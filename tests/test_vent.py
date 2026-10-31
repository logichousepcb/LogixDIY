"""Logix Vent tests."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any

from homeassistant.components.cover import CoverState
from homeassistant.components.light import (
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
)
from homeassistant.config_entries import SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.logixdiy.const import DOMAIN, EVENT_BUTTON_ACTION

from .conftest import posted, setup_entry

VENT_HOST = "192.168.22.41"
VENT_BASE = f"http://{VENT_HOST}"
VENT_ID = "b48a0ad0b171"

COVER = "cover.logix_vent_b171"
LIGHT = "light.logix_vent_b171_status_light"

# Copied from a Logix Vent running firmware 1.2.0.
VENT_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixvent",
    "name": "Logix Vent",
    "id": VENT_ID,
    "mac": "B4:8A:0A:D0:B1:71",
    "hostname": "basementvent",
    "ip": VENT_HOST,
    "fw": "1.2.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "buttons": 1,
        "actions": ["single"],
        "vent": {"runTimeMs": 10000, "supportsStop": True, "supportsPosition": False},
        "statusLight": {"type": "rgb", "effects": ["None", "Pulse", "Fast Pulse"]},
    },
    "mqtt": {"enabled": False, "connected": False},
}

VENT_STATUS: dict[str, Any] = {
    "title": "Logix Vent",
    "version": "1.2.0",
    "mode": "station",
    "connected": True,
    "ip": VENT_HOST,
    "rssi": -54,
    "hostname": "basementvent",
    "mac": "B4:8A:0A:D0:B1:71",
    "uptime": 11,
    "heap": 35656,
    "authEnabled": False,
}


def make_vent(
    state: str = "closed",
    operation: str = "idle",
    count: int = 0,
    light_state: str = "on",
    hex_color: str = "#00ff00",
    effect: str = "None",
) -> dict[str, Any]:
    """Build a Logix Vent GET /api/controller response."""
    rgb = [int(hex_color[i : i + 2], 16) for i in (1, 3, 5)]
    return {
        "uptimeMs": 11549,
        "buttons": [
            {
                "pressed": False,
                "pressCount": count,
                "lastAction": "single" if count else "none",
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "vent": {
            "state": state,
            "operation": operation,
            "moving": operation != "idle",
            "remainingMs": 9000 if operation != "idle" else 0,
        },
        "light": {
            "state": light_state,
            "brightness": 255,
            "color": dict(zip("rgb", rgb, strict=True)),
            "hex": hex_color,
            "effect": effect,
        },
    }


OK = {"ok": True}


def mock_vent(aioclient_mock: AiohttpClientMocker, controller: dict[str, Any] | None = None) -> None:
    """Register every endpoint of a healthy Logix Vent."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{VENT_BASE}/api/info", json=VENT_INFO)
    aioclient_mock.get(f"{VENT_BASE}/api/controller", json=controller or make_vent())
    aioclient_mock.get(f"{VENT_BASE}/api/status", json=VENT_STATUS)
    for path in ("/api/vent", "/api/light", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{VENT_BASE}{path}", json=OK)


@pytest.fixture
def vent_entry() -> MockConfigEntry:
    """A config entry for the test vent."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=VENT_ID, title="Logix Vent B171", data={CONF_HOST: VENT_HOST}
    )


async def test_vent_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, vent_entry: MockConfigEntry
) -> None:
    """The vent, status light, button event, restart and sensors are created; no Logix 3 entities."""
    mock_vent(aioclient_mock)
    await setup_entry(hass, vent_entry)
    assert vent_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(vent_entry.runtime_data.device_id)
    assert device.model == "Logix Vent"
    assert device.model_id == "logixvent"
    assert device.sw_version == "1.2.0"

    assert hass.states.get(COVER).state == CoverState.CLOSED
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (0, 255, 0)
    assert light.attributes[ATTR_EFFECT] == EFFECT_OFF
    assert light.attributes[ATTR_EFFECT_LIST] == [EFFECT_OFF, "pulse", "fast_pulse"]
    assert hass.states.get("event.logix_vent_b171_button_1") is not None
    assert hass.states.get("button.logix_vent_b171_restart") is not None
    assert hass.states.get("sensor.logix_vent_b171_wi_fi_signal").state == "-54"

    entities = er.async_entries_for_config_entry(er.async_get(hass), vent_entry.entry_id)
    assert not [e for e in entities if e.domain in ("select", "number")]
    press = er.async_get(hass).async_get("button.logix_vent_b171_button_1_single_press")
    assert press is not None and press.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert await hass.config_entries.async_unload(vent_entry.entry_id)


async def test_vent_cover(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, vent_entry: MockConfigEntry
) -> None:
    """Open, close and stop post the action; a running motor shows as opening."""
    mock_vent(aioclient_mock)
    await setup_entry(hass, vent_entry)

    mock_vent(aioclient_mock, make_vent(state="open", operation="opening"))
    await hass.services.async_call("cover", "open_cover", {ATTR_ENTITY_ID: COVER}, blocking=True)
    assert posted(aioclient_mock, "/api/vent", VENT_BASE) == [{"action": "open"}]
    state = hass.states.get(COVER)
    assert state.state == CoverState.OPENING
    assert state.attributes["remaining_ms"] == 9000

    await hass.services.async_call("cover", "stop_cover", {ATTR_ENTITY_ID: COVER}, blocking=True)
    await hass.services.async_call("cover", "close_cover", {ATTR_ENTITY_ID: COVER}, blocking=True)
    assert posted(aioclient_mock, "/api/vent", VENT_BASE)[-2:] == [{"action": "stop"}, {"action": "close"}]


async def test_vent_light(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, vent_entry: MockConfigEntry
) -> None:
    """The status light maps HA effects and colors to the device's light endpoint."""
    mock_vent(aioclient_mock, make_vent(hex_color="#0000ff", effect="Fast Pulse"))
    await setup_entry(hass, vent_entry)
    assert hass.states.get(LIGHT).attributes[ATTR_EFFECT] == "fast_pulse"

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, "rgb_color": (0, 0, 255), "brightness": 128, "effect": "fast_pulse"},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/light", VENT_BASE)[-1] == {
        "state": "on",
        "hex": "#0000ff",
        "brightness": 128,
        "effect": "Fast Pulse",
    }

    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: LIGHT, "effect": EFFECT_OFF}, blocking=True
    )
    assert posted(aioclient_mock, "/api/light", VENT_BASE)[-1] == {"state": "on", "effect": "None"}

    await hass.services.async_call(
        "light", "turn_off", {ATTR_ENTITY_ID: LIGHT, "transition": 2}, blocking=True
    )
    assert posted(aioclient_mock, "/api/light", VENT_BASE)[-1] == {"state": "off", "transition": 2}

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_led_colors", {ATTR_ENTITY_ID: LIGHT, "single_color": [255, 0, 0]}, blocking=True
        )


async def test_vent_button_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, vent_entry: MockConfigEntry
) -> None:
    """A physical press (actionCount going up) fires button 1 single."""
    mock_vent(aioclient_mock)
    await setup_entry(hass, vent_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    coordinator = vent_entry.runtime_data

    mock_vent(aioclient_mock, make_vent(state="open", operation="opening", count=1))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single")]
    assert hass.states.get("event.logix_vent_b171_button_1").attributes["event_type"] == "single"


async def test_vent_zeroconf(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A discovered Logix Vent can be added."""
    mock_vent(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(VENT_HOST),
            ip_addresses=[ip_address(VENT_HOST)],
            hostname="basementvent.local.",
            name="basementvent._logix._tcp.local.",
            port=80,
            type="_logix._tcp.local.",
            properties={"id": VENT_ID, "model": "logixvent", "fw": "1.2.0", "api": "1"},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Logix Vent B171"
    assert result["data"] == {CONF_HOST: VENT_HOST}
