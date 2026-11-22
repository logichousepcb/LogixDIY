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


def _parse_light(light: dict[str, Any]) -> StatusLight:
    return StatusLight(
        on=light["state"] == "on",
        brightness=int(light["brightness"]),
        color=hex_to_rgb(light["hex"]),
        effect=light["effect"],
    )


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
                light=_parse_light(light),
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
class TemperatureReading:
    """The Logix GR's temperature sensor."""

    celsius: float | None  # with the device's calibration offset; None while it has no reading


@dataclass(frozen=True, slots=True)
class OutletState:
    """Parsed GET /api/controller of a Logix Outlet, Logix Plug 3, Logix Energy Plug, Logix S31
    Plug, Logix Plug, Logix RGB Plug, Logix RGB Switch, Logix 3-Way Switch or Logix GR.

    The Logix GR's one outlet is its momentary garage relay: on only during a pulse. The Logix
    3-Way Switch's one outlet is the light, as sensed on the light circuit.
    """

    buttons: tuple[ButtonState, ...]
    outlets: tuple[bool, ...]  # on/off, in outlet order (1 = top)
    energy: EnergyReading | None  # None on devices without a meter (Logix Plug, Logix RGB Plug)
    light: StatusLight | None = None  # the Logix RGB Plug's and Logix GR's light
    temperature: TemperatureReading | None = None  # the Logix GR's sensor

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> OutletState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            energy = data.get("energy")
            light = data.get("light")
            temperature = data.get("temperature")
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
                light=None if light is None else _parse_light(light),
                temperature=None
                if temperature is None
                else TemperatureReading(celsius=float(temperature["celsius"]) if temperature["ok"] else None),
            )
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise LogixConnectionError(f"Unexpected outlet state: {err!r}") from err


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class ProbeReading:
    """One DS18B20 of a Logix Temp."""

    key: str  # temp, temp2, ...
    name: str
    address: str  # ROM address, 16 hex digits
    celsius: float | None  # with the device's calibration offset; None while offline
    min_celsius: float | None  # since the device booted
    max_celsius: float | None


@dataclass(frozen=True, slots=True)
class TempState:
    """Parsed GET /api/controller of a Logix Temp (or its MQTT state topic)."""

    probes: tuple[ProbeReading, ...]
    buttons: tuple[ButtonState, ...] = ()  # none; here for the coordinator's action tracking

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TempState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            return cls(
                probes=tuple(
                    ProbeReading(
                        key=s["key"],
                        name=s["name"],
                        address=s["address"],
                        celsius=_optional_float(s["temperatureC"]) if s["online"] else None,
                        min_celsius=_optional_float(s.get("minC")),
                        max_celsius=_optional_float(s.get("maxC")),
                    )
                    for s in data["sensors"]
                ),
            )
        except (KeyError, TypeError, ValueError, IndexError) as err:
            raise LogixConnectionError(f"Unexpected temperature state: {err!r}") from err


@dataclass(frozen=True, slots=True)
class FixtureState:
    """Parsed GET /api/state of a Logix Fixture (an addressable LED strip or string).

    The whole strip is one light: on/off, master brightness, one color and an effect, which
    animates at `speed`.
    """

    on: bool
    brightness: int  # 0-255
    color: RGB
    effect: str  # effect name, e.g. "Solid" or "Christmas"
    speed: int  # 0-255
    buttons: tuple[ButtonState, ...] = ()  # none; here for the coordinator's action tracking

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> FixtureState:
        """Build from the device's JSON; raises LogixConnectionError if it is malformed."""
        try:
            red, green, blue = (int(c) for c in data["color"])
            return cls(
                on=bool(data["on"]),
                brightness=int(data["bri"]),
                color=(red, green, blue),
                effect=str(data["effectName"]),
                speed=int(data["speed"]),
            )
        except (KeyError, TypeError, ValueError) as err:
            raise LogixConnectionError(f"Unexpected fixture state: {err!r}") from err


def fixture_status(info: dict[str, Any]) -> dict[str, Any]:
    """The Logix Fixture has no /api/status; its /api/info carries the same diagnostics."""
    wifi = info.get("wifi") or {}
    return {
        "version": info.get("version"),
        "ip": wifi.get("ip"),
        "rssi": wifi.get("rssi"),
        "connected": wifi.get("connected"),
    }


type LogixState = ControllerState | VentState | OutletState | TempState | FixtureState


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
            # The Logix Fixture uses an API token instead of an admin password; it reads it from
            # X-Api-Key when Authorization isn't a Bearer token. The other devices ignore it.
            self._headers["X-Api-Key"] = password
        # The ESP8266 web server handles one connection at a time; queue requests here rather
        # than have them time out on the device.
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """URL of the device's web page."""
        return f"http://{self.host}"

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        async with self._lock:
            try:
                async with (
                    asyncio.timeout(REQUEST_TIMEOUT),
                    self._session.request(
                        method,
                        f"{self.base_url}{path}",
                        data=data,
                        json=json,
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
        # The Logix Fixture names these "version" and "auth"; use the family's names.
        if "fw" not in info and isinstance(info.get("version"), str):
            info["fw"] = info["version"]
        if "authRequired" not in info and isinstance(info.get("auth"), bool):
            info["authRequired"] = info["auth"]
        return info

    async def get_status(self, path: str = "/api/status") -> dict[str, Any]:
        """Firmware, network and system status."""
        return await self._request("GET", path)

    async def get_controller[T: LogixState](
        self,
        parse: Callable[[dict[str, Any]], T] = ControllerState.from_json,
        path: str = "/api/controller",
    ) -> T:
        """Live state from /api/controller (/api/state on a Logix Fixture), parsed by the model's
        state class."""
        return parse(await self._request("GET", path))

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

    async def trigger(self) -> None:
        """Logix GR: pulse the garage relay, like pressing the door's wall button."""
        await self._request("POST", "/api/trigger")

    async def read_now(self) -> None:
        """Logix Temp: take a reading now instead of waiting for the next interval."""
        await self._request("POST", "/api/controller/read")

    async def set_state(self, fields: dict[str, Any]) -> None:
        """Logix Fixture: change on, bri, color, effect or speed (a JSON body)."""
        await self._request("POST", "/api/state", json=fields)

    async def get_effects(self) -> list[str]:
        """Logix Fixture: effect names, in id order."""
        effects = await self._request("GET", "/api/effects")
        try:
            return [str(e["name"]) for e in sorted(effects, key=lambda e: int(e["id"]))]
        except (KeyError, TypeError, ValueError) as err:
            raise LogixConnectionError(f"Unexpected effect list: {err!r}") from err

    async def identify(self) -> None:
        """Logix Fixture: blink the LEDs white for about 3 seconds."""
        await self._request("POST", "/api/identify")

    async def reboot(self) -> None:
        """Restart the device."""
        await self._request("POST", "/api/reboot")
