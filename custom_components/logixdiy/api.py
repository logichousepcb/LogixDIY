"""Async HTTP client for Logix devices."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

ADMIN_USER = "admin"
REQUEST_TIMEOUT = 5

type RGB = tuple[int, int, int]


class LogixError(Exception):
    """Base error for Logix devices."""


class LogixConnectionError(LogixError):
    """The device could not be reached or sent an unreadable reply."""


class LogixAuthError(LogixError):
    """The device rejected the admin password."""


class LogixCommandError(LogixError):
    """The device refused a command (HTTP 400)."""


def hex_to_rgb(value: str) -> RGB:
    """Convert "#rrggbb" to an RGB tuple."""
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to "#rrggbb"."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


@dataclass(frozen=True, slots=True)
class ButtonState:
    """One physical button."""

    pressed: bool
    last_action: str | None
    action_count: int


@dataclass(frozen=True, slots=True)
class LedState:
    """One RGB LED: its current state and the color for each state."""

    state: str
    colors: tuple[RGB, ...]  # one per action, in the order of capabilities.actions
    off_color: RGB


def _parse_buttons(data: dict[str, Any]) -> tuple[ButtonState, ...]:
    return tuple(
        ButtonState(
            pressed=bool(b["pressed"]),
            last_action=None if b["lastAction"] == "none" else b["lastAction"],
            action_count=int(b["actionCount"]),
        )
        for b in data["buttons"]
    )


@dataclass(frozen=True, slots=True)
class ControllerState:
    """Parsed GET /api/controller (or the MQTT state topic, which omits live timing fields)."""

    buttons: tuple[ButtonState, ...]
    leds: tuple[LedState, ...]
    brightness: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ControllerState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            return cls(
                buttons=_parse_buttons(data),
                leds=tuple(
                    LedState(
                        state=led["state"],
                        colors=tuple(hex_to_rgb(c) for c in led["colors"]),
                        off_color=hex_to_rgb(led["offColor"]),
                    )
                    for led in data["leds"]
                ),
                brightness=int(data["brightness"]),
            )
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise LogixConnectionError(f"Unexpected controller state: {err!r}") from err


@dataclass(frozen=True, slots=True)
class StatusLight:
    """A single RGB status light with brightness and effects."""

    on: bool
    brightness: int
    color: RGB
    effect: str


@dataclass(frozen=True, slots=True)
class VentState:
    """Parsed GET /api/controller of a Logix Vent."""

    buttons: tuple[ButtonState, ...]
    vent_state: str  # open or closed
    operation: str  # idle, opening or closing
    remaining_ms: int
    light: StatusLight

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> VentState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            vent = data["vent"]
            light = data["light"]
            return cls(
                buttons=_parse_buttons(data),
                vent_state=vent["state"],
                operation=vent["operation"],
                remaining_ms=int(vent.get("remainingMs", 0)),
                light=StatusLight(
                    on=light["state"] == "on",
                    brightness=int(light["brightness"]),
                    color=hex_to_rgb(light["hex"]),
                    effect=light["effect"],
                ),
            )
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise LogixConnectionError(f"Unexpected vent state: {err!r}") from err


@dataclass(frozen=True, slots=True)
class EnergyReading:
    """The Logix Outlet's energy meter (one meter for all outlets), as Tasmota reports it."""

    voltage: float  # V
    current: float  # A
    power: float  # W
    apparent_power: float  # VA
    reactive_power: float  # var
    factor: float  # 0-1
    today: float  # kWh
    yesterday: float  # kWh
    total: float  # kWh
    total_start_time: str | None  # local ISO time the total started counting


@dataclass(frozen=True, slots=True)
class OutletState:
    """Parsed GET /api/controller of a Logix Outlet or Logix Plug."""

    buttons: tuple[ButtonState, ...]
    outlets: tuple[bool, ...]  # on/off, in outlet order (1 = top)
    energy: EnergyReading | None  # None on devices without a meter (Logix Plug)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> OutletState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            energy = data.get("energy")
            return cls(
                buttons=_parse_buttons(data),
                outlets=tuple(o["state"] == "on" for o in data["outlets"]),
                energy=None
                if energy is None
                else EnergyReading(
                    voltage=float(energy["voltage"]),
                    current=float(energy["current"]),
                    power=float(energy["power"]),
                    apparent_power=float(energy["apparentPower"]),
                    reactive_power=float(energy["reactivePower"]),
                    factor=float(energy["factor"]),
                    today=float(energy["today"]),
                    yesterday=float(energy["yesterday"]),
                    total=float(energy["total"]),
                    total_start_time=energy.get("totalStartTime") or None,
                ),
            )
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise LogixConnectionError(f"Unexpected outlet state: {err!r}") from err


type LogixState = ControllerState | VentState | OutletState


class LogixClient:
    """Talks to one Logix device over its HTTP API."""

    def __init__(self, session: aiohttp.ClientSession, host: str, password: str | None = None) -> None:
        """Initialize the client."""
        self.host = host
        self._session = session
        self._headers = {"Connection": "close"}
        if password:
            token = base64.b64encode(f"{ADMIN_USER}:{password}".encode()).decode()
            self._headers["Authorization"] = f"Basic {token}"
        # The ESP8266 web server handles one connection at a time; queue requests here rather
        # than have them time out on the device.
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """URL of the device's web page."""
        return f"http://{self.host}"

    async def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        async with self._lock:
            try:
                async with (
                    asyncio.timeout(REQUEST_TIMEOUT),
                    self._session.request(
                        method,
                        f"{self.base_url}{path}",
                        data=data,
                        headers=self._headers,
                    ) as resp,
                ):
                    if resp.status == 401:
                        raise LogixAuthError("Invalid admin password")
                    status = resp.status
                    body = await resp.json(content_type=None)
            except LogixError:
                raise
            except (TimeoutError, aiohttp.ClientError, ValueError) as err:
                raise LogixConnectionError(f"Error talking to {self.host}: {err!r}") from err

        if status == 400 or (isinstance(body, dict) and body.get("ok") is False):
            message = (body.get("message") or body.get("error")) if isinstance(body, dict) else None
            raise LogixCommandError(message or f"HTTP {status}")
        if status >= 300:
            raise LogixConnectionError(f"Unexpected HTTP {status} from {self.host}")
        return body

    async def get_info(self) -> dict[str, Any]:
        """Identity and capabilities; never needs a password."""
        info = await self._request("GET", "/api/info")
        if not isinstance(info, dict) or not info.get("id") or not info.get("model"):
            raise LogixConnectionError(f"{self.host} is not a Logix device")
        return info

    async def get_status(self) -> dict[str, Any]:
        """Firmware, network and system status."""
        return await self._request("GET", "/api/status")

    async def get_controller[T: LogixState](
        self, parse: Callable[[dict[str, Any]], T] = ControllerState.from_json
    ) -> T:
        """Live state from /api/controller, parsed by the model's state class."""
        return parse(await self._request("GET", "/api/controller"))

    async def set_controller(self, fields: dict[str, Any]) -> None:
        """Set any LED colors, LED states or brightness (POST /api/controller keys)."""
        await self._request("POST", "/api/controller", fields)

    async def press(self, button: int, action: str) -> None:
        """Simulate a button action exactly like the physical button."""
        await self._request("POST", "/api/controller/press", {"button": button, "presses": action})

    async def set_brightness(self, brightness: int) -> None:
        """Set brightness 0-255; the device debounces the flash write."""
        await self._request("POST", "/api/controller/brightness", {"brightness": brightness})

    async def set_vent(self, action: str) -> None:
        """Logix Vent: open, close, stop or toggle."""
        await self._request("POST", "/api/vent", {"action": action})

    async def set_light(self, fields: dict[str, Any]) -> None:
        """Logix Vent status light: state, brightness, hex, effect, transition."""
        await self._request("POST", "/api/light", fields)

    async def set_outlet(self, outlet: int, state: str) -> None:
        """Logix Outlet: switch outlet 1-N on, off or toggle."""
        await self._request("POST", "/api/outlet", {"outlet": outlet, "state": state})

    async def reboot(self) -> None:
        """Restart the device."""
        await self._request("POST", "/api/reboot")
