"""Async HTTP client for Logix devices."""

from __future__ import annotations

import asyncio
import base64
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
                buttons=tuple(
                    ButtonState(
                        pressed=bool(b["pressed"]),
                        last_action=None if b["lastAction"] == "none" else b["lastAction"],
                        action_count=int(b["actionCount"]),
                    )
                    for b in data["buttons"]
                ),
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
            message = body.get("message") if isinstance(body, dict) else None
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

    async def get_controller(self) -> ControllerState:
        """Button and LED state."""
        return ControllerState.from_json(await self._request("GET", "/api/controller"))

    async def set_controller(self, fields: dict[str, Any]) -> None:
        """Set any LED colors, LED states or brightness (POST /api/controller keys)."""
        await self._request("POST", "/api/controller", fields)

    async def press(self, button: int, action: str) -> None:
        """Simulate a button action exactly like the physical button."""
        await self._request("POST", "/api/controller/press", {"button": button, "presses": action})

    async def set_brightness(self, brightness: int) -> None:
        """Set brightness 0-255; the device debounces the flash write."""
        await self._request("POST", "/api/controller/brightness", {"brightness": brightness})

    async def reboot(self) -> None:
        """Restart the device."""
        await self._request("POST", "/api/reboot")
