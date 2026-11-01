"""Logix Plug tests."""

from __future__ import annotations

import copy
import json
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
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

PLUG_HOST = "192.168.22.57"
PLUG_BASE = f"http://{PLUG_HOST}"
PLUG_ID = "68c63a97c4c9"
PLUG_TOPIC = f"logixplug/{PLUG_ID}"

SWITCH = "switch.entry_table_lamp"

# Copied from the Geekbes YM-WS-1 running Logix Plug firmware 1.0.0.
PLUG_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixplug",
    "name": "Entry Table Lamp",
    "id": PLUG_ID,
    "mac": "68:C6:3A:97:C4:C9",
    "hostname": "entry-table-lamp",
    "ip": PLUG_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["plug"],
        "outletNames": ["Entry Table Lamp"],
        "actions": ["single"],
        "energy": False,
        "energyMeters": 0,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": PLUG_TOPIC},
}

PLUG_STATUS: dict[str, Any] = {
    "title": "Logix Plug",
    "name": "Entry Table Lamp",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": PLUG_HOST,
    "rssi": -61,
    "hostname": "entry-table-lamp",
    "mac": "68:C6:3A:97:C4:C9",
    "uptime": 17,
    "heap": 36016,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": True,
    "button": False,
}


def make_plug(state: str = "off", count: int = 0) -> dict[str, Any]:
    """Build a Logix Plug GET /api/controller response."""
    return {
        "uptimeMs": 17953,
        "name": "Entry Table Lamp",
        "outlets": [{"outlet": 1, "key": "plug", "name": "Entry Table Lamp", "state": state}],
        "buttons": [
            {
                "button": 1,
                "key": "plug",
                "pressed": False,
                "pressCount": count,
                "lastAction": "single" if count else "none",
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
    }


OK = {"ok": True, "message": "Plug on.", "restart": False}


def mock_plug(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix Plug."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{PLUG_BASE}/api/info", json=info or PLUG_INFO)
    aioclient_mock.get(f"{PLUG_BASE}/api/controller", json=controller or make_plug())
    aioclient_mock.get(f"{PLUG_BASE}/api/status", json=PLUG_STATUS)
    for path in ("/api/outlet", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{PLUG_BASE}{path}", json=OK)


@pytest.fixture
def plug_entry() -> MockConfigEntry:
    """A config entry for the test plug."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=PLUG_ID, title="Entry Table Lamp", data={CONF_HOST: PLUG_HOST}
    )


async def test_plug_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """One switch named after the device, one button event; no energy or LED entities."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)
    assert plug_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(plug_entry.runtime_data.device_id)
    assert device.model == "Logix Plug"
    assert device.model_id == "logixplug"

    switch = hass.states.get(SWITCH)
    assert switch.state == STATE_OFF
    assert switch.attributes["device_class"] == "outlet"
    assert switch.attributes["friendly_name"] == "Entry Table Lamp"

    assert hass.states.get("event.entry_table_lamp_button_1") is not None
    assert hass.states.get("button.entry_table_lamp_restart") is not None
    assert hass.states.get("sensor.entry_table_lamp_wi_fi_signal").state == "-61"

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, plug_entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "switch"] == [SWITCH]
    assert not [e for e in entities if e.domain in ("light", "select", "number", "cover")]
    assert not [e for e in entities if "energy" in e.unique_id or "power" in e.unique_id]

    assert await hass.config_entries.async_unload(plug_entry.entry_id)


async def test_plug_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """Turning the switch on, off or toggling it posts outlet 1 to /api/outlet."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)

    mock_plug(aioclient_mock, make_plug(state="on"))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", PLUG_BASE) == [{"outlet": 1, "state": "on"}]
    assert hass.states.get(SWITCH).state == STATE_ON

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    await hass.services.async_call("switch", "toggle", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", PLUG_BASE)[-2:] == [
        {"outlet": 1, "state": "off"},
        {"outlet": 1, "state": "toggle"},
    ]


async def test_plug_button_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """A physical press fires button 1 single and the switch follows the relay."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_plug(aioclient_mock, make_plug(state="on", count=1))
    await plug_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single")]
    assert hass.states.get(SWITCH).state == STATE_ON


async def test_plug_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    plug_entry: MockConfigEntry,
) -> None:
    """The device's MQTT state topic, which has no energy block, updates the switch."""
    info = copy.deepcopy(PLUG_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": PLUG_TOPIC}
    mock_plug(aioclient_mock, info=info)
    await setup_entry(hass, plug_entry)
    assert plug_entry.runtime_data.mqtt_topic == PLUG_TOPIC

    state = make_plug(state="on")
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{PLUG_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{PLUG_TOPIC}/button/1/action", "single")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single")]
