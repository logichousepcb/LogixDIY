"""Logix Outlet tests."""

from __future__ import annotations

import copy
from ipaddress import ip_address
import json
from typing import Any

from homeassistant.config_entries import SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_mqtt_message,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import MqttMockHAClient

from custom_components.logixdiy.const import DOMAIN, EVENT_BUTTON_ACTION

from .conftest import posted, setup_entry

OUTLET_HOST = "192.168.22.80"
OUTLET_BASE = f"http://{OUTLET_HOST}"
OUTLET_ID = "c4dd573121fb"
OUTLET_TOPIC = f"logixoutlet/{OUTLET_ID}"

TOP = "switch.family_room_outlet_top"
BOTTOM = "switch.family_room_outlet_bottom"

# Copied from the Gosund WO1 running Logix Outlet firmware 1.0.0.
OUTLET_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixoutlet",
    "name": "Family Room Outlet",
    "id": OUTLET_ID,
    "mac": "C4:DD:57:31:21:FB",
    "hostname": "family-room-outlet",
    "ip": OUTLET_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 2,
        "buttons": 2,
        "outletKeys": ["top", "bottom"],
        "outletNames": ["Family Room Outlet Top", "Family Room Outlet Bottom"],
        "actions": ["single"],
        "energy": True,
        "energyMeters": 1,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": OUTLET_TOPIC},
}

OUTLET_STATUS: dict[str, Any] = {
    "title": "Logix Outlet",
    "name": "Family Room Outlet",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": OUTLET_HOST,
    "rssi": -49,
    "hostname": "family-room-outlet",
    "mac": "C4:DD:57:31:21:FB",
    "uptime": 738,
    "heap": 32808,
    "authEnabled": False,
}


def make_outlet(
    top: str = "on",
    bottom: str = "off",
    counts: tuple[int, int] = (0, 0),
    power: float = 0.0,
) -> dict[str, Any]:
    """Build a Logix Outlet GET /api/controller response."""
    keys = ("top", "bottom")
    return {
        "uptimeMs": 738720,
        "name": "Family Room Outlet",
        "outlets": [
            {"outlet": i + 1, "key": keys[i], "name": f"Family Room Outlet {keys[i].title()}", "state": state}
            for i, state in enumerate((top, bottom))
        ],
        "buttons": [
            {
                "button": i + 1,
                "key": keys[i],
                "pressed": False,
                "pressCount": counts[i],
                "lastAction": "single" if counts[i] else "none",
                "actionCount": counts[i],
                "lastActionMsAgo": 100 if counts[i] else None,
            }
            for i in range(2)
        ],
        "energy": {
            "voltage": 120.4,
            "current": 0.5 if power else 0.0,
            "power": power,
            "apparentPower": 61.0 if power else 0.0,
            "reactivePower": 11.0 if power else 0.0,
            "factor": 0.98 if power else 0.0,
            "today": 0.125,
            "yesterday": 0.456,
            "total": 32.223,
            "totalStartTime": "2022-06-26T07:24:20",
        },
    }


OK = {"ok": True, "message": "Outlet top on.", "restart": False}


def mock_outlet(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix Outlet."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{OUTLET_BASE}/api/info", json=info or OUTLET_INFO)
    aioclient_mock.get(f"{OUTLET_BASE}/api/controller", json=controller or make_outlet())
    aioclient_mock.get(f"{OUTLET_BASE}/api/status", json=OUTLET_STATUS)
    for path in ("/api/outlet", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{OUTLET_BASE}{path}", json=OK)


@pytest.fixture
def outlet_entry() -> MockConfigEntry:
    """A config entry for the test outlet."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=OUTLET_ID, title="Family Room Outlet", data={CONF_HOST: OUTLET_HOST}
    )


async def test_outlet_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, outlet_entry: MockConfigEntry
) -> None:
    """Two outlet switches, energy sensors, two button events; no LED entities."""
    mock_outlet(aioclient_mock)
    await setup_entry(hass, outlet_entry)
    assert outlet_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(outlet_entry.runtime_data.device_id)
    assert device.model == "Logix Outlet"
    assert device.model_id == "logixoutlet"

    assert hass.states.get(TOP).state == STATE_ON
    assert hass.states.get(TOP).attributes["device_class"] == "outlet"
    assert hass.states.get(BOTTOM).state == STATE_OFF

    assert hass.states.get("sensor.family_room_outlet_voltage").state == "120.4"
    assert hass.states.get("sensor.family_room_outlet_power").state == "0.0"
    assert hass.states.get("sensor.family_room_outlet_energy_today").state == "0.125"
    assert hass.states.get("sensor.family_room_outlet_energy_yesterday").state == "0.456"
    total = hass.states.get("sensor.family_room_outlet_energy_total")
    assert total.state == "32.223"
    assert total.attributes["state_class"] == "total_increasing"
    assert total.attributes["total_start_time"] == "2022-06-26T07:24:20"

    assert hass.states.get("event.family_room_outlet_button_1") is not None
    assert hass.states.get("event.family_room_outlet_button_2") is not None
    assert hass.states.get("button.family_room_outlet_restart") is not None

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, outlet_entry.entry_id)
    assert not [e for e in entities if e.domain in ("light", "select", "number", "cover")]
    # The less common meter readings start disabled.
    apparent = registry.async_get("sensor.family_room_outlet_apparent_power")
    assert apparent is not None and apparent.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert await hass.config_entries.async_unload(outlet_entry.entry_id)


async def test_outlet_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, outlet_entry: MockConfigEntry
) -> None:
    """Turning a switch on, off or toggling it posts to /api/outlet and picks up the new state."""
    mock_outlet(aioclient_mock)
    await setup_entry(hass, outlet_entry)

    mock_outlet(aioclient_mock, make_outlet(top="on", bottom="on", power=60.0))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: BOTTOM}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", OUTLET_BASE) == [{"outlet": 2, "state": "on"}]
    assert hass.states.get(BOTTOM).state == STATE_ON
    assert hass.states.get("sensor.family_room_outlet_power").state == "60.0"

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: TOP}, blocking=True)
    await hass.services.async_call("switch", "toggle", {ATTR_ENTITY_ID: TOP}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", OUTLET_BASE)[-2:] == [
        {"outlet": 1, "state": "off"},
        {"outlet": 1, "state": "toggle"},
    ]


async def test_outlet_button_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, outlet_entry: MockConfigEntry
) -> None:
    """A physical press of the bottom button fires button 2 single."""
    mock_outlet(aioclient_mock)
    await setup_entry(hass, outlet_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_outlet(aioclient_mock, make_outlet(bottom="on", counts=(0, 1)))
    await outlet_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(2, "single")]
    assert hass.states.get(BOTTOM).state == STATE_ON


async def test_outlet_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    outlet_entry: MockConfigEntry,
) -> None:
    """The device's MQTT state topic updates the switches and energy sensors."""
    info = copy.deepcopy(OUTLET_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": OUTLET_TOPIC}
    mock_outlet(aioclient_mock, info=info)
    await setup_entry(hass, outlet_entry)
    assert outlet_entry.runtime_data.mqtt_topic == OUTLET_TOPIC

    state = make_outlet(top="off", bottom="on", power=60.0)
    del state["uptimeMs"]
    for button in state["buttons"]:
        del button["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{OUTLET_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(TOP).state == STATE_OFF
    assert hass.states.get(BOTTOM).state == STATE_ON
    assert hass.states.get("sensor.family_room_outlet_power").state == "60.0"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{OUTLET_TOPIC}/button/1/action", "single")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single")]


@pytest.mark.parametrize(
    ("name", "title"),
    [("Family Room Outlet", "Family Room Outlet"), ("Logix Outlet", "Logix Outlet 21FB")],
)
async def test_outlet_zeroconf(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, name: str, title: str
) -> None:
    """A discovered outlet is titled with its own name, or the model name plus ID if it has none."""
    info = copy.deepcopy(OUTLET_INFO)
    info["name"] = name
    mock_outlet(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(OUTLET_HOST),
            ip_addresses=[ip_address(OUTLET_HOST)],
            hostname="family-room-outlet.local.",
            name="family-room-outlet._logix._tcp.local.",
            port=80,
            type="_logix._tcp.local.",
            properties={"id": OUTLET_ID, "model": "logixoutlet", "fw": "1.0.0", "api": "1", "name": name},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == title
    assert result["data"] == {CONF_HOST: OUTLET_HOST}
