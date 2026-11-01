"""Logix RGB Switch tests."""

from __future__ import annotations

import copy
import json
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
)
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

SW_HOST = "192.168.22.102"
SW_BASE = f"http://{SW_HOST}"
SW_ID = "84f3eb648bf0"
SW_TOPIC = f"logixrgbswitch/{SW_ID}"

SWITCH = "switch.kauff2"
LIGHT = "light.kauff2_button_light"

# Copied from the KAUF SRF10 wall switch running Logix RGB Switch firmware 1.0.0.
SW_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixrgbswitch",
    "name": "kauff2",
    "id": SW_ID,
    "mac": "84:F3:EB:64:8B:F0",
    "hostname": "kauff2",
    "ip": SW_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["plug"],
        "outletNames": ["kauff2"],
        "actions": ["single", "double"],
        "statusLight": {"type": "rgb", "effects": ["None", "Pulse", "Fast Pulse"]},
        "energy": False,
        "energyMeters": 0,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": SW_TOPIC},
}

SW_STATUS: dict[str, Any] = {
    "title": "Logix RGB Switch",
    "name": "kauff2",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": SW_HOST,
    "rssi": -67,
    "hostname": "kauff2",
    "mac": "84:F3:EB:64:8B:F0",
    "uptime": 796,
    "heap": 33456,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": True,
    "button": False,
    "light": "off, #ffffff, brightness 26/255, effect None",
}


def make_rgb_switch(
    state: str = "off",
    count: int = 0,
    action: str = "single",
    light_state: str = "off",
    light_hex: str = "#ffffff",
    brightness: int = 26,
    effect: str = "None",
) -> dict[str, Any]:
    """Build a Logix RGB Switch GET /api/controller response."""
    return {
        "uptimeMs": 114207,
        "name": "kauff2",
        "outlets": [{"outlet": 1, "key": "plug", "name": "kauff2", "state": state}],
        "buttons": [
            {
                "button": 1,
                "key": "plug",
                "pressed": False,
                "pressCount": count,
                "lastAction": action if count else "none",
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "light": {"state": light_state, "brightness": brightness, "hex": light_hex, "effect": effect},
    }


OK = {"ok": True, "message": "Light on.", "restart": False}


def mock_rgb_switch(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix RGB Switch."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{SW_BASE}/api/info", json=info or SW_INFO)
    aioclient_mock.get(f"{SW_BASE}/api/controller", json=controller or make_rgb_switch())
    aioclient_mock.get(f"{SW_BASE}/api/status", json=SW_STATUS)
    for path in ("/api/outlet", "/api/light", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{SW_BASE}{path}", json=OK)


@pytest.fixture
def sw_entry() -> MockConfigEntry:
    """A config entry for the test wall switch."""
    return MockConfigEntry(domain=DOMAIN, unique_id=SW_ID, title="kauff2", data={CONF_HOST: SW_HOST})


async def test_rgb_switch_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """One switch (device class switch) named after the device, a "Button light", button events."""
    mock_rgb_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    assert sw_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(sw_entry.runtime_data.device_id)
    assert device.model == "Logix RGB Switch"
    assert device.model_id == "logixrgbswitch"

    switch = hass.states.get(SWITCH)
    assert switch.state == STATE_OFF
    assert switch.attributes["device_class"] == "switch"
    assert switch.attributes["friendly_name"] == "kauff2"

    light = hass.states.get(LIGHT)
    assert light.state == STATE_OFF
    assert light.attributes["friendly_name"] == "kauff2 Button light"
    assert light.attributes[ATTR_EFFECT_LIST] == [EFFECT_OFF, "pulse", "fast_pulse"]

    event = hass.states.get("event.kauff2_button_1")
    assert event.attributes["event_types"] == ["single", "double"]

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, sw_entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "switch"] == [SWITCH]
    assert [e.entity_id for e in entities if e.domain == "light"] == [LIGHT]
    assert not [e for e in entities if e.domain in ("select", "number", "cover")]
    assert not [e for e in entities if "energy" in e.unique_id or "power" in e.unique_id]
    assert sorted(e.entity_id for e in entities if e.domain == "button") == [
        "button.kauff2_button_1_double_press",
        "button.kauff2_button_1_single_press",
        "button.kauff2_restart",
    ]

    assert await hass.config_entries.async_unload(sw_entry.entry_id)


async def test_rgb_switch_relay_and_light(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """The switch posts outlet 1 to /api/outlet, the light posts to /api/light."""
    mock_rgb_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)

    mock_rgb_switch(aioclient_mock, make_rgb_switch(state="on"))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", SW_BASE) == [{"outlet": 1, "state": "on"}]
    assert posted(aioclient_mock, "/api/light", SW_BASE) == []
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get(LIGHT).state == STATE_OFF

    green = make_rgb_switch(state="on", light_state="on", light_hex="#00ff00", brightness=200)
    mock_rgb_switch(aioclient_mock, green)
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, ATTR_RGB_COLOR: (0, 255, 0), ATTR_BRIGHTNESS: 200},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/light", SW_BASE) == [
        {"state": "on", "hex": "#00ff00", "brightness": 200}
    ]
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (0, 255, 0)
    assert light.attributes[ATTR_BRIGHTNESS] == 200


async def test_rgb_switch_button_events(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, sw_entry: MockConfigEntry
) -> None:
    """A single press fires single and switches the relay; a double press fires double and the light."""
    mock_rgb_switch(aioclient_mock)
    await setup_entry(hass, sw_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_rgb_switch(aioclient_mock, make_rgb_switch(state="on", count=1))
    await sw_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    mock_rgb_switch(aioclient_mock, make_rgb_switch(state="on", count=2, action="double", light_state="on"))
    await sw_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single"), (1, "double")]
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get(LIGHT).state == STATE_ON


async def test_rgb_switch_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    sw_entry: MockConfigEntry,
) -> None:
    """The MQTT state topic updates the switch and the light; button actions fire events."""
    info = copy.deepcopy(SW_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": SW_TOPIC}
    mock_rgb_switch(aioclient_mock, info=info)
    await setup_entry(hass, sw_entry)
    assert sw_entry.runtime_data.mqtt_topic == SW_TOPIC

    state = make_rgb_switch(state="on", light_state="on", light_hex="#0000ff", effect="Pulse")
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{SW_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (0, 0, 255)
    assert light.attributes[ATTR_EFFECT] == "pulse"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{SW_TOPIC}/button/1/action", "single")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single")]
