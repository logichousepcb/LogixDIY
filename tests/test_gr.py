"""Logix GR tests."""

from __future__ import annotations

import copy
import json
from typing import Any

from homeassistant.components.light import ATTR_EFFECT_LIST, ATTR_RGB_COLOR, EFFECT_OFF
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
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

GR_HOST = "192.168.22.50"
GR_BASE = f"http://{GR_HOST}"
GR_ID = "48551900dd75"
GR_TOPIC = f"logixgr/{GR_ID}"

TRIGGER = "button.garage_opener_trigger"
LIGHT = "light.garage_opener_button_light"
TEMPERATURE = "sensor.garage_opener_temperature"

# Copied from the Logix GR board running Logix GR firmware 1.0.0.
GR_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixgr",
    "name": "Garage Opener",
    "id": GR_ID,
    "mac": "48:55:19:00:DD:75",
    "hostname": "garage-opener",
    "ip": GR_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["relay"],
        "outletNames": ["Garage Opener"],
        "momentary": True,
        "pulseMs": 2400,
        "buttonDecoupled": True,
        "actions": ["single", "double", "triple", "hold"],
        "holdMs": 4000,
        "statusLight": {"type": "rgb", "effects": ["None", "Pulse", "Fast Pulse"]},
        "temperature": True,
        "energy": False,
        "energyMeters": 0,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": GR_TOPIC},
}

GR_STATUS: dict[str, Any] = {
    "title": "Logix GR",
    "name": "Garage Opener",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": GR_HOST,
    "rssi": -53,
    "hostname": "garage-opener",
    "mac": "48:55:19:00:DD:75",
    "uptime": 86,
    "heap": 33552,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": True,
    "button": False,
    "relay": False,
    "sensor": "287105380C322013",
    "light": "off, #69e6ff, brightness 153/255, effect None",
}


def make_gr(
    relay: str = "off",
    count: int = 0,
    action: str = "single",
    light_state: str = "off",
    celsius: float | None = 17.9,
) -> dict[str, Any]:
    """Build a Logix GR GET /api/controller response."""
    ok = celsius is not None
    return {
        "uptimeMs": 86972,
        "name": "Garage Opener",
        "outlets": [
            {
                "outlet": 1,
                "key": "relay",
                "name": "Garage Opener",
                "state": relay,
                "pulseMs": 2400,
                "triggerCount": 1 if relay == "on" else 0,
                "remainingMs": 1800 if relay == "on" else 0,
            }
        ],
        "buttons": [
            {
                "button": 1,
                "key": "button",
                "pressed": False,
                "pressCount": count,
                "lastAction": action if count else "none",
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "light": {"state": light_state, "brightness": 153, "hex": "#69e6ff", "effect": "None"},
        "temperature": {
            "ok": ok,
            "value": round(celsius * 1.8 + 32, 1) if ok else None,
            "celsius": celsius,
            "unit": "F",
            "offset": -6,
            "sensor": "287105380C322013",
        },
    }


OK = {"ok": True, "message": "Relay pulsed for 2.4 s.", "restart": False}


def mock_gr(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix GR."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{GR_BASE}/api/info", json=info or GR_INFO)
    aioclient_mock.get(f"{GR_BASE}/api/controller", json=controller or make_gr())
    aioclient_mock.get(f"{GR_BASE}/api/status", json=GR_STATUS)
    for path in ("/api/trigger", "/api/light", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{GR_BASE}{path}", json=OK)


@pytest.fixture
def gr_entry() -> MockConfigEntry:
    """A config entry for the test Logix GR."""
    return MockConfigEntry(domain=DOMAIN, unique_id=GR_ID, title="Garage Opener", data={CONF_HOST: GR_HOST})


async def test_gr_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, gr_entry: MockConfigEntry
) -> None:
    """A trigger button, a button light, a temperature sensor and button events; no switch."""
    mock_gr(aioclient_mock)
    await setup_entry(hass, gr_entry)
    assert gr_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(gr_entry.runtime_data.device_id)
    assert device.model == "Logix GR"
    assert device.model_id == "logixgr"

    assert hass.states.get(TRIGGER).attributes["friendly_name"] == "Garage Opener Trigger"

    light = hass.states.get(LIGHT)
    assert light.state == STATE_OFF
    assert light.attributes["friendly_name"] == "Garage Opener Button light"
    assert light.attributes[ATTR_EFFECT_LIST] == [EFFECT_OFF, "pulse", "fast_pulse"]

    temperature = hass.states.get(TEMPERATURE)
    assert float(temperature.state) == 17.9
    assert temperature.attributes["device_class"] == "temperature"
    assert temperature.attributes["unit_of_measurement"] == "°C"

    event = hass.states.get("event.garage_opener_button_1")
    assert event.attributes["event_types"] == ["single", "double", "triple", "hold"]

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, gr_entry.entry_id)
    assert not [e for e in entities if e.domain in ("switch", "select", "number", "cover")]
    assert not [e for e in entities if "energy" in e.unique_id or "power" in e.unique_id]
    assert [e.entity_id for e in entities if e.domain == "light"] == [LIGHT]
    assert sorted(e.entity_id for e in entities if e.domain == "button") == [
        "button.garage_opener_button_1_double_press",
        "button.garage_opener_button_1_hold",
        "button.garage_opener_button_1_single_press",
        "button.garage_opener_button_1_triple_press",
        "button.garage_opener_restart",
        TRIGGER,
    ]
    # The trigger is the point of the device; the simulated presses are opt-in.
    assert not registry.async_get(TRIGGER).disabled
    assert registry.async_get("button.garage_opener_button_1_single_press").disabled

    assert await hass.config_entries.async_unload(gr_entry.entry_id)


async def test_gr_trigger(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, gr_entry: MockConfigEntry
) -> None:
    """The trigger button posts to /api/trigger and nothing else."""
    mock_gr(aioclient_mock)
    await setup_entry(hass, gr_entry)

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: TRIGGER}, blocking=True)
    assert posted(aioclient_mock, "/api/trigger", GR_BASE) == [None]
    assert posted(aioclient_mock, "/api/controller/press", GR_BASE) == []
    assert posted(aioclient_mock, "/api/light", GR_BASE) == []


async def test_gr_temperature_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, gr_entry: MockConfigEntry
) -> None:
    """The sensor goes unavailable while the device has no reading, and comes back with one."""
    mock_gr(aioclient_mock, make_gr(celsius=None))
    await setup_entry(hass, gr_entry)
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE

    mock_gr(aioclient_mock, make_gr(celsius=18.4))
    await gr_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(TEMPERATURE).state) == 18.4


async def test_gr_button_events(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, gr_entry: MockConfigEntry
) -> None:
    """Button actions fire events; the decoupled button leaves the light alone."""
    mock_gr(aioclient_mock)
    await setup_entry(hass, gr_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_gr(aioclient_mock, make_gr(count=1))
    await gr_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    mock_gr(aioclient_mock, make_gr(count=2, action="hold"))
    await gr_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "single"), (1, "hold")]
    assert hass.states.get(LIGHT).state == STATE_OFF


async def test_gr_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    gr_entry: MockConfigEntry,
) -> None:
    """The MQTT state topic updates the light and the temperature; button actions fire events."""
    info = copy.deepcopy(GR_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": GR_TOPIC}
    mock_gr(aioclient_mock, info=info)
    await setup_entry(hass, gr_entry)
    assert gr_entry.runtime_data.mqtt_topic == GR_TOPIC

    state = make_gr(relay="on", light_state="on", celsius=19.2)
    del state["uptimeMs"]
    del state["outlets"][0]["remainingMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{GR_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes[ATTR_RGB_COLOR] == (0x69, 0xE6, 0xFF)
    assert float(hass.states.get(TEMPERATURE).state) == 19.2
    assert gr_entry.runtime_data.data.outlets == (True,)

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{GR_TOPIC}/button/1/action", "triple")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "triple")]
