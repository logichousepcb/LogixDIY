"""Logix Energy Plug tests."""

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

PLUG_HOST = "192.168.22.220"
PLUG_BASE = f"http://{PLUG_HOST}"
PLUG_ID = "b4e62d16c6bd"
PLUG_TOPIC = f"logixenergyplug/{PLUG_ID}"

SWITCH = "switch.pow1725"

# The AWP04L plug running Logix Energy Plug firmware 1.0.0 (see its API.md).
PLUG_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixenergyplug",
    "name": "pow1725",
    "id": PLUG_ID,
    "mac": "B4:E6:2D:16:C6:BD",
    "hostname": "pow1725",
    "ip": PLUG_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 1,
        "buttons": 1,
        "outletKeys": ["plug"],
        "outletNames": ["pow1725"],
        "actions": ["single", "double", "triple", "hold"],
        "multiPressMs": 400,
        "holdMs": 1000,
        "energy": True,
        "energyMeters": 1,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": PLUG_TOPIC},
}

PLUG_STATUS: dict[str, Any] = {
    "title": "Logix Energy Plug",
    "name": "pow1725",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": PLUG_HOST,
    "rssi": -54,
    "hostname": "pow1725",
    "mac": "B4:E6:2D:16:C6:BD",
    "uptime": 95,
    "heap": 30112,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": False,
    "button": False,
}


def make_plug(state: str = "off", count: int = 0, last: str = "none", power: float = 0.0) -> dict[str, Any]:
    """Build a Logix Energy Plug GET /api/controller response."""
    return {
        "uptimeMs": 95120,
        "name": "pow1725",
        "buttonMode": "normal",
        "outlets": [{"outlet": 1, "key": "plug", "name": "pow1725", "state": state}],
        "buttons": [
            {
                "button": 1,
                "key": "plug",
                "pressed": False,
                "pressCount": count,
                "lastAction": last,
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "energy": {
            "voltage": 120.4,
            "current": 0.5 if power else 0.0,
            "power": power,
            "apparentPower": 61.0 if power else 0.0,
            "reactivePower": 11.0 if power else 0.0,
            "factor": 0.98 if power else 0.0,
            "today": 0.042,
            "yesterday": 0.311,
            "total": 1.234,
            "totalStartTime": "2026-11-07T05:00:00",
        },
    }


OK = {"ok": True, "message": "Plug on.", "restart": False}


def mock_plug(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix Energy Plug."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{PLUG_BASE}/api/info", json=info or PLUG_INFO)
    aioclient_mock.get(f"{PLUG_BASE}/api/controller", json=controller or make_plug())
    aioclient_mock.get(f"{PLUG_BASE}/api/status", json=PLUG_STATUS)
    for path in ("/api/outlet", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{PLUG_BASE}{path}", json=OK)


@pytest.fixture
def plug_entry() -> MockConfigEntry:
    """A config entry for the test plug."""
    return MockConfigEntry(domain=DOMAIN, unique_id=PLUG_ID, title="pow1725", data={CONF_HOST: PLUG_HOST})


async def test_energyplug_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """One switch named after the device, energy sensors, one button event with four actions."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)
    assert plug_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(plug_entry.runtime_data.device_id)
    assert device.model == "Logix Energy Plug"
    assert device.model_id == "logixenergyplug"

    switch = hass.states.get(SWITCH)
    assert switch.state == STATE_OFF
    assert switch.attributes["device_class"] == "outlet"
    assert switch.attributes["friendly_name"] == "pow1725"

    assert hass.states.get("sensor.pow1725_voltage").state == "120.4"
    assert hass.states.get("sensor.pow1725_power").state == "0.0"
    total = hass.states.get("sensor.pow1725_energy_total")
    assert total.state == "1.234"
    assert total.attributes["state_class"] == "total_increasing"

    event = hass.states.get("event.pow1725_button_1")
    assert event.attributes["event_types"] == ["single", "double", "triple", "hold"]
    assert hass.states.get("button.pow1725_restart") is not None

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, plug_entry.entry_id)
    assert [e.entity_id for e in entities if e.domain == "switch"] == [SWITCH]
    assert not [e for e in entities if e.domain in ("light", "select", "number", "cover")]
    presses = sorted(e.entity_id for e in entities if e.domain == "button" and "button_1" in e.entity_id)
    assert presses == [
        "button.pow1725_button_1_double_press",
        "button.pow1725_button_1_hold",
        "button.pow1725_button_1_single_press",
        "button.pow1725_button_1_triple_press",
    ]
    assert all(registry.async_get(p).disabled_by is er.RegistryEntryDisabler.INTEGRATION for p in presses)

    assert await hass.config_entries.async_unload(plug_entry.entry_id)


async def test_energyplug_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """Turning the switch on, off or toggling it posts outlet 1 to /api/outlet."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)

    mock_plug(aioclient_mock, make_plug(state="on", power=60.0))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", PLUG_BASE) == [{"outlet": 1, "state": "on"}]
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get("sensor.pow1725_power").state == "60.0"

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    await hass.services.async_call("switch", "toggle", {ATTR_ENTITY_ID: SWITCH}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", PLUG_BASE)[-2:] == [
        {"outlet": 1, "state": "off"},
        {"outlet": 1, "state": "toggle"},
    ]


async def test_energyplug_button_press(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """The press buttons send the action to /api/controller/press."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)
    registry = er.async_get(hass)
    for action in ("single_press", "hold"):
        registry.async_update_entity(f"button.pow1725_button_1_{action}", disabled_by=None)
    await hass.config_entries.async_reload(plug_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.pow1725_button_1_single_press"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.pow1725_button_1_hold"}, blocking=True
    )
    assert posted(aioclient_mock, "/api/controller/press", PLUG_BASE) == [
        {"button": 1, "presses": "single"},
        {"button": 1, "presses": "hold"},
    ]


async def test_energyplug_button_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, plug_entry: MockConfigEntry
) -> None:
    """A physical double press, seen on a poll, fires button 1 double."""
    mock_plug(aioclient_mock)
    await setup_entry(hass, plug_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_plug(aioclient_mock, make_plug(count=1, last="double"))
    await plug_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "double")]


async def test_energyplug_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    plug_entry: MockConfigEntry,
) -> None:
    """The device's MQTT state topic updates the switch; actions arrive on their own topic."""
    info = copy.deepcopy(PLUG_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": PLUG_TOPIC}
    mock_plug(aioclient_mock, info=info)
    await setup_entry(hass, plug_entry)
    assert plug_entry.runtime_data.mqtt_topic == PLUG_TOPIC

    state = make_plug(state="on", power=60.0)
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{PLUG_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_ON
    assert hass.states.get("sensor.pow1725_power").state == "60.0"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{PLUG_TOPIC}/button/1/action", "triple")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "triple")]


@pytest.mark.parametrize(
    ("name", "title"),
    [("pow1725", "pow1725"), ("Logix Energy Plug", "Logix Energy Plug C6BD")],
)
async def test_energyplug_zeroconf(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, name: str, title: str
) -> None:
    """A discovered plug is titled with its own name, or the model name plus ID if it has none."""
    info = copy.deepcopy(PLUG_INFO)
    info["name"] = name
    mock_plug(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(PLUG_HOST),
            ip_addresses=[ip_address(PLUG_HOST)],
            hostname="pow1725.local.",
            name="pow1725._logix._tcp.local.",
            port=80,
            type="_logix._tcp.local.",
            properties={"id": PLUG_ID, "model": "logixenergyplug", "fw": "1.0.0", "api": "1", "name": name},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == title
    assert result["data"] == {CONF_HOST: PLUG_HOST}
