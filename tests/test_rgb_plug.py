"""Logix RGB Plug tests."""

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

RGB_HOST = "192.168.22.79"
RGB_BASE = f"http://{RGB_HOST}"
RGB_ID = "b4e62d0af887"
RGB_TOPIC = f"logixrgbplug/{RGB_ID}"

SWITCH = "switch.xtool_m1"
LIGHT = "light.xtool_m1_light"

# Copied from the RGB night-light plug running Logix RGB Plug firmware 1.0.0.
RGB_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixrgbplug",
    "name": "xTool M1",
    "id": RGB_ID,
    "mac": "B4:E6:2D:0A:F8:87",
    "hostname": "xtool-m1",
    "ip": RGB_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["plug"],
        "outletNames": ["xTool M1"],
        "actions": ["single", "double"],
        "statusLight": {"type": "rgb", "effects": ["None", "Pulse", "Fast Pulse"]},
        "energy": False,
        "energyMeters": 0,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": RGB_TOPIC},
}

RGB_STATUS: dict[str, Any] = {
    "title": "Logix RGB Plug",
    "name": "xTool M1",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": RGB_HOST,
    "rssi": -64,
    "hostname": "xtool-m1",
    "mac": "B4:E6:2D:0A:F8:87",
    "uptime": 19,
    "heap": 34976,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": True,
    "button": False,
    "light": "off, #ffffff, brightness 26/255, effect None",
}


def make_rgb_plug(
    state: str = "off",
    count: int = 0,
    action: str = "single",
    light_state: str = "off",
    light_hex: str = "#ffffff",
    brightness: int = 26,
    effect: str = "None",
) -> dict[str, Any]:
    """Build a Logix RGB Plug GET /api/controller response."""
    return {
        "uptimeMs": 19707,
        "name": "xTool M1",
        "outlets": [{"outlet": 1, "key": "plug", "name": "xTool M1", "state": state}],
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


def mock_rgb_plug(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix RGB Plug."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{RGB_BASE}/api/info", json=info or RGB_INFO)
    aioclient_mock.get(f"{RGB_BASE}/api/controller", json=controller or make_rgb_plug())
    aioclient_mock.get(f"{RGB_BASE}/api/status", json=RGB_STATUS)
    for path in ("/api/outlet", "/api/light", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{RGB_BASE}{path}", json=OK)


@pytest.fixture
def rgb_entry() -> MockConfigEntry:
    """A config entry for the test RGB plug."""
    return MockConfigEntry(domain=DOMAIN, unique_id=RGB_ID, title="xTool M1", data={CONF_HOST: RGB_HOST})


async def test_rgb_plug_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rgb_entry: MockConfigEntry
) -> None:
    """One switch named after the device, one light named "Light", button events; no energy."""
    mock_rgb_plug(aioclient_mock)
    await setup_entry(hass, rgb_entry)
    assert rgb_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(rgb_entry.runtime_data.device_id)
    assert device.model == "Logix RGB Plug"
    assert device.model_id == "logixrgbplug"

    switch = hass.states.get(SWITCH)
    assert switch.state == STATE_OFF
    assert switch.attributes["device_class"] == "outlet"
    assert switch.attributes["friendly_name"] == "xTool M1"

    light = hass.states.get(LIGHT)
    assert light.state == STATE_OFF
    assert light.attributes["friendly_name"] == "xTool M1 Light"
    assert light.attributes[ATTR_EFFECT_LIST] == [EFFECT_OFF, "pulse", "fast_pulse"]

    event = hass.states.get("event.xtool_m1_button_1")
    assert event.attributes["event_types"] == ["single", "double"]

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, rgb_entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "switch"] == [SWITCH]
    assert [e.entity_id for e in entities if e.domain == "light"] == [LIGHT]
    assert not [e for e in entities if e.domain in ("select", "number", "cover")]
    assert not [e for e in entities if "energy" in e.unique_id or "power" in e.unique_id]
    assert sorted(e.entity_id for e in entities if e.domain == "button") == [
        "button.xtool_m1_button_1_double_press",
        "button.xtool_m1_button_1_single_press",
        "button.xtool_m1_restart",
    ]

    assert await hass.config_entries.async_unload(rgb_entry.entry_id)


async def test_rgb_plug_light(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rgb_entry: MockConfigEntry
) -> None:
    """The light posts color, brightness, effect and transition to /api/light."""
    mock_rgb_plug(aioclient_mock)
    await setup_entry(hass, rgb_entry)

    mock_rgb_plug(aioclient_mock, make_rgb_plug(light_state="on", light_hex="#ff0000", brightness=128))
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, ATTR_RGB_COLOR: (255, 0, 0), ATTR_BRIGHTNESS: 128, ATTR_EFFECT: "pulse"},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/light", RGB_BASE) == [
        {"state": "on", "hex": "#ff0000", "brightness": 128, "effect": "Pulse"}
    ]
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (255, 0, 0)
    assert light.attributes[ATTR_BRIGHTNESS] == 128

    await hass.services.async_call("light", "turn_off", {ATTR_ENTITY_ID: LIGHT, "transition": 2}, blocking=True)
    assert posted(aioclient_mock, "/api/light", RGB_BASE)[-1] == {"state": "off", "transition": 2}


async def test_rgb_plug_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rgb_entry: MockConfigEntry
) -> None:
    """The switch posts outlet 1 to /api/outlet; the light is left alone."""
    mock_rgb_plug(aioclient_mock)
    await setup_entry(hass, rgb_entry)

    mock_rgb_plug(aioclient_mock, make_rgb_plug(state="on"))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", RGB_BASE) == [{"outlet": 1, "state": "on"}]
    assert posted(aioclient_mock, "/api/light", RGB_BASE) == []
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get(LIGHT).state == STATE_OFF


async def test_rgb_plug_button_events(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, rgb_entry: MockConfigEntry
) -> None:
    """A single press fires single and switches the relay; a double press fires double and the light."""
    mock_rgb_plug(aioclient_mock)
    await setup_entry(hass, rgb_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_rgb_plug(aioclient_mock, make_rgb_plug(state="on", count=1))
    await rgb_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    mock_rgb_plug(aioclient_mock, make_rgb_plug(state="on", count=2, action="double", light_state="on"))
    await rgb_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single"), (1, "double")]
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get(LIGHT).state == STATE_ON


async def test_rgb_plug_press(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entity_registry: er.EntityRegistry,
    rgb_entry: MockConfigEntry,
) -> None:
    """The press buttons (disabled by default) post presses=single or presses=double."""
    mock_rgb_plug(aioclient_mock)
    await setup_entry(hass, rgb_entry)
    for action in ("single", "double"):
        entity_registry.async_update_entity(f"button.xtool_m1_button_1_{action}_press", disabled_by=None)
    await hass.config_entries.async_reload(rgb_entry.entry_id)
    await hass.async_block_till_done()

    for action in ("single", "double"):
        await hass.services.async_call(
            "button", "press", {ATTR_ENTITY_ID: f"button.xtool_m1_button_1_{action}_press"}, blocking=True
        )
    assert posted(aioclient_mock, "/api/controller/press", RGB_BASE) == [
        {"button": 1, "presses": "single"},
        {"button": 1, "presses": "double"},
    ]


async def test_rgb_plug_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    rgb_entry: MockConfigEntry,
) -> None:
    """The MQTT state topic updates the switch and the light; button actions fire events."""
    info = copy.deepcopy(RGB_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": RGB_TOPIC}
    mock_rgb_plug(aioclient_mock, info=info)
    await setup_entry(hass, rgb_entry)
    assert rgb_entry.runtime_data.mqtt_topic == RGB_TOPIC

    state = make_rgb_plug(state="on", light_state="on", light_hex="#0000ff", effect="Fast Pulse")
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{RGB_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (0, 0, 255)
    assert light.attributes[ATTR_EFFECT] == "fast_pulse"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{RGB_TOPIC}/button/1/action", "double")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "double")]
