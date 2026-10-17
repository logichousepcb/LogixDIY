"""Fixtures for LogixDIY tests."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.logixdiy.const import DOMAIN

HOST = "192.168.22.235"
BASE = f"http://{HOST}"
DEVICE_ID = "48e72971e527"
TOPIC = f"logix3/{DEVICE_ID}"

# Shapes copied from the Logix 3 firmware 1.2.0 API reference.
INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logix3",
    "name": "Logix 3",
    "id": DEVICE_ID,
    "mac": "48:E7:29:71:E5:27",
    "hostname": "esp12f-e527",
    "ip": HOST,
    "fw": "1.2.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "buttons": 3,
        "leds": 3,
        "ledType": "rgb",
        "brightness": True,
        "actions": ["single", "double", "triple", "hold"],
        "ledStates": ["off", "single", "double", "triple", "hold"],
        "multiPressMs": 400,
        "holdMs": 3000,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": TOPIC},
}

COLORS = ["#ff4040", "#ffa000", "#ffffff", "#8000ff"]


def make_controller(
    states: tuple[str, str, str] = ("off", "double", "off"),
    counts: tuple[int, int, int] = (0, 0, 0),
    last: tuple[str, str, str] = ("none", "none", "none"),
    brightness: int = 255,
) -> dict[str, Any]:
    """Build a GET /api/controller response."""
    modes = ["off", "single", "double", "triple", "hold"]
    return {
        "uptimeMs": 31946,
        "buttons": [
            {
                "pressed": False,
                "pressCount": counts[i],
                "lastAction": last[i],
                "actionCount": counts[i],
                "lastActionMsAgo": 100 if counts[i] else None,
            }
            for i in range(3)
        ],
        "leds": [
            {
                "mode": modes.index(states[i]),
                "state": states[i],
                "colors": COLORS,
                "offColor": "#000000",
            }
            for i in range(3)
        ],
        "brightness": brightness,
        "multiPressMs": 400,
        "holdMs": 3000,
    }


STATUS: dict[str, Any] = {
    "title": "Logix 3",
    "version": "1.2.0",
    "mode": "station",
    "savedSsid": "home",
    "connected": True,
    "ip": HOST,
    "rssi": -58,
    "hostname": "esp12f-e527",
    "mac": "48:E7:29:71:E5:27",
    "uptime": 31,
    "heap": 30000,
    "authEnabled": False,
}

OK = {"ok": True, "message": "LED settings saved."}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/logixdiy."""


def mock_device(
    aioclient_mock: AiohttpClientMocker,
    info: dict[str, Any] | None = None,
    controller: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy device."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/info", json=info or INFO)
    aioclient_mock.get(f"{BASE}/api/controller", json=controller or make_controller())
    aioclient_mock.get(f"{BASE}/api/status", json=STATUS)
    for path in ("/api/controller", "/api/controller/press", "/api/controller/brightness", "/api/reboot"):
        aioclient_mock.post(f"{BASE}{path}", json=OK)


@pytest.fixture
def info() -> dict[str, Any]:
    """A mutable copy of the device info."""
    return copy.deepcopy(INFO)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the test device."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DEVICE_ID,
        title="Logix 3 E527",
        data={CONF_HOST: HOST},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


def posted(aioclient_mock: AiohttpClientMocker, path: str) -> list[dict[str, Any]]:
    """Form data of every POST to `path`."""
    return [
        data
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url) == f"{BASE}{path}"
    ]
