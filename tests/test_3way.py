"""Logix 3-Way Switch tests."""

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

SW_HOST = "192.168.22.133"
SW_BASE = f"http://{SW_HOST}"
SW_ID = "bcddc28d061f"
SW_TOPIC = f"logix3way/{SW_ID}"

SWITCH = "switch.garage_light"

# Copied from the Moes 3-way wall switch running Logix 3-Way Switch firmware 1.0.0.
SW_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logix3way",
    "name": "Garage Light",
    "id": SW_ID,
    "mac": "BC:DD:C2:8D:06:1F",
    "hostname": "garage-light",
    "ip": SW_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["light"],
        "outletNames": ["Garage Light"],
        "actions": ["single", "double", "triple", "hold"],
        "multiPressMs": 400,
        "holdMs": 1000,
        "energy": False,
        "threeWay": True,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": SW_TOPIC},
}

SW_STATUS: dict[str, Any] = {
    "title": "Logix 3-Way Switch",
    "name": "Garage Light",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": SW_HOST,
    "rssi": -57,
    "channel": 1,
    "hostname": "garage-light",
    "mac": "BC:DD:C2:8D:06:1F",
    "uptime": 596,
    "heap": 34704,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": True,
    "button": False,
    "senseRaw": "high",
    "senseEdges": 0,
    "traveler": 1,
    "remoteChanges": 0,
}


def make_switch(
    state: str = "off", count: int = 0, action: str = "single", traveler: int = 1, remote: int = 0
) -> dict[str, Any]:
    """Build a Logix 3-Way Switch GET /api/controller response."""
    return {
        "uptimeMs": 596162,
        "name": "Garage Light",
        "buttonMode": "normal",
        "senseMode": "normal",
        "outlets": [
            {
                "outlet": 1,
                "key": "light",
                "name": "Garage Light",
                "state": state,
                "sensed": state,
                "settling": False,
                "traveler": traveler,
            }
        ],
        "buttons": [
            {
                "button": 1,
                "key": "light",
                "pressed": False,
                "pressCount": count,
                "lastAction": action if count else "none",
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "remoteChanges": remote,
    }


OK = {"ok": True, "message": "Light on.", "restart": False}


def mock_switch(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix 3-Way Switch."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{SW_BASE}/api/info", json=info or SW_INFO)
    aioclient_mock.get(f"{SW_BASE}/api/controller", json=controller or make_switch())
    aioclient_mock.get(f"{SW_BASE}/api/status", json=SW_STATUS)
    for path in ("/api/outlet", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{SW_BASE}{path}", json=OK)


@pytest.fixture
def sw_entry() -> MockConfigEntry:
    """A config entry for the test switch."""
    return MockConfigEntry(domain=DOMAIN, unique_id=SW_ID, title="Garage Light", data={CONF_HOST: SW_HOST})


async def test_3way_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """One switch named after the device (class switch), one button event; no energy or lights."""
    mock_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    assert sw_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(sw_entry.runtime_data.device_id)
    assert device.model == "Logix 3-Way Switch"
    assert device.model_id == "logix3way"

    switch = hass.states.get(SWITCH)
    assert switch.state == STATE_OFF
    assert switch.attributes["device_class"] == "switch"
    assert switch.attributes["friendly_name"] == "Garage Light"

    event = hass.states.get("event.garage_light_button_1")
    assert event.attributes["event_types"] == ["single", "double", "triple", "hold"]
    assert hass.states.get("button.garage_light_restart") is not None
    assert hass.states.get("sensor.garage_light_wi_fi_signal").state == "-57"

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, sw_entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "switch"] == [SWITCH]
    assert len([e for e in entities if e.unique_id.startswith(f"{SW_ID}_button_1_")]) == 4
    assert not [e for e in entities if e.domain in ("light", "select", "number", "cover")]
    assert not [e for e in entities if "energy" in e.unique_id or "power" in e.unique_id]

    assert await hass.config_entries.async_unload(sw_entry.entry_id)


async def test_3way_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """On, off and toggle post outlet 1 to /api/outlet; the device decides whether to flip."""
    mock_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)

    mock_switch(aioclient_mock, make_switch(state="on", traveler=0))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", SW_BASE) == [{"outlet": 1, "state": "on"}]
    assert hass.states.get(SWITCH).state == STATE_ON

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    await hass.services.async_call("switch", "toggle", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", SW_BASE)[-2:] == [
        {"outlet": 1, "state": "off"},
        {"outlet": 1, "state": "toggle"},
    ]


async def test_3way_other_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """The light turned on at the other 3-way switch: the state follows, no button event fires."""
    mock_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_switch(aioclient_mock, make_switch(state="on", remote=1))
    await sw_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON
    assert events == []


async def test_3way_button_events(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """A physical single press toggles the light; a hold is only reported."""
    mock_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_switch(aioclient_mock, make_switch(state="on", count=1, traveler=0))
    await sw_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON

    mock_switch(aioclient_mock, make_switch(state="on", count=2, action="hold", traveler=0))
    await sw_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single"), (1, "hold")]
    assert hass.states.get(SWITCH).state == STATE_ON


async def test_3way_press(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """The (disabled by default) press buttons post the action to /api/controller/press."""
    mock_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    registry = er.async_get(hass)
    for action in ("single_press", "hold"):
        registry.async_update_entity(f"button.garage_light_button_1_{action}", disabled_by=None)
    await hass.config_entries.async_reload(sw_entry.entry_id)
    await hass.async_block_till_done()

    for action in ("single_press", "hold"):
        await hass.services.async_call(
            "button", "press", {ATTR_ENTITY_ID: f"button.garage_light_button_1_{action}"}, blocking=True
        )
    assert posted(aioclient_mock, "/api/controller/press", SW_BASE) == [
        {"button": 1, "presses": "single"},
        {"button": 1, "presses": "hold"},
    ]


async def test_3way_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    sw_entry: MockConfigEntry,
) -> None:
    """The MQTT state topic (sent on every change, the other switch included) updates the switch."""
    info = copy.deepcopy(SW_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": SW_TOPIC}
    mock_switch(aioclient_mock, info=info)
    await setup_entry(hass, sw_entry)
    assert sw_entry.runtime_data.mqtt_topic == SW_TOPIC

    state = make_switch(state="on", remote=1)
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{SW_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{SW_TOPIC}/button/1/action", "triple")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "triple")]
