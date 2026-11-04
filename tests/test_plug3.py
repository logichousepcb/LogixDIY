"""Logix Plug 3 tests."""

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

STRIP_HOST = "192.168.22.231"
STRIP_BASE = f"http://{STRIP_HOST}"
STRIP_ID = "bcddc2ee0420"
STRIP_TOPIC = f"logixplug3/{STRIP_ID}"

OUTLET_1 = "switch.garage_4_outlet_outlet_1"
OUTLET_2 = "switch.garage_4_outlet_outlet_2"
OUTLET_3 = "switch.garage_4_outlet_outlet_3"

# The KMC 4 Outlet power strip running Logix Plug 3 firmware 1.0.0 (see its API.md).
STRIP_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixplug3",
    "name": "Garage 4 Outlet",
    "id": STRIP_ID,
    "mac": "BC:DD:C2:EE:04:20",
    "hostname": "garage-4-outlet",
    "ip": STRIP_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 3,
        "buttons": 1,
        "outletKeys": ["outlet1", "outlet2", "outlet3"],
        "outletNames": ["Garage 4 Outlet Outlet 1", "Garage 4 Outlet Outlet 2", "Garage 4 Outlet Outlet 3"],
        "actions": ["single", "double", "triple", "hold"],
        "multiPressMs": 400,
        "holdMs": 1000,
        "energy": True,
        "energyMeters": 1,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": STRIP_TOPIC},
}

STRIP_STATUS: dict[str, Any] = {
    "title": "Logix Plug 3",
    "name": "Garage 4 Outlet",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": STRIP_HOST,
    "rssi": -74,
    "hostname": "garage-4-outlet",
    "mac": "BC:DD:C2:EE:04:20",
    "uptime": 95,
    "heap": 30112,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": False,
    "button": False,
}


def make_strip(
    states: tuple[str, str, str] = ("on", "off", "off"),
    count: int = 0,
    last: str = "none",
    power: float = 0.0,
) -> dict[str, Any]:
    """Build a Logix Plug 3 GET /api/controller response."""
    return {
        "uptimeMs": 95120,
        "name": "Garage 4 Outlet",
        "buttonMode": "normal",
        "outlets": [
            {
                "outlet": i + 1,
                "key": f"outlet{i + 1}",
                "name": f"Garage 4 Outlet Outlet {i + 1}",
                "state": state,
            }
            for i, state in enumerate(states)
        ],
        "buttons": [
            {
                "button": 1,
                "key": "button",
                "pressed": False,
                "pressCount": count,
                "lastAction": last,
                "actionCount": count,
                "lastActionMsAgo": 100 if count else None,
            }
        ],
        "energy": {
            "voltage": 121.7,
            "current": 0.5 if power else 0.0,
            "power": power,
            "apparentPower": 61.0 if power else 0.0,
            "reactivePower": 11.0 if power else 0.0,
            "factor": 0.98 if power else 0.0,
            "today": 0.042,
            "yesterday": 0.311,
            "total": 104.127,
            "totalStartTime": "2020-10-29T20:14:51",
        },
    }


OK = {"ok": True, "message": "Outlet 1 on.", "restart": False}


def mock_strip(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix Plug 3."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{STRIP_BASE}/api/info", json=info or STRIP_INFO)
    aioclient_mock.get(f"{STRIP_BASE}/api/controller", json=controller or make_strip())
    aioclient_mock.get(f"{STRIP_BASE}/api/status", json=STRIP_STATUS)
    for path in ("/api/outlet", "/api/controller/press", "/api/reboot"):
        aioclient_mock.post(f"{STRIP_BASE}{path}", json=OK)


@pytest.fixture
def strip_entry() -> MockConfigEntry:
    """A config entry for the test strip."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=STRIP_ID, title="Garage 4 Outlet", data={CONF_HOST: STRIP_HOST}
    )


async def test_plug3_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, strip_entry: MockConfigEntry
) -> None:
    """Three outlet switches, energy sensors, one button event with four actions; no lights."""
    mock_strip(aioclient_mock)
    await setup_entry(hass, strip_entry)
    assert strip_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(strip_entry.runtime_data.device_id)
    assert device.model == "Logix Plug 3"
    assert device.model_id == "logixplug3"

    assert hass.states.get(OUTLET_1).state == STATE_ON
    assert hass.states.get(OUTLET_1).attributes["device_class"] == "outlet"
    assert hass.states.get(OUTLET_1).attributes["friendly_name"] == "Garage 4 Outlet Outlet 1"
    assert hass.states.get(OUTLET_2).state == STATE_OFF
    assert hass.states.get(OUTLET_3).state == STATE_OFF

    assert hass.states.get("sensor.garage_4_outlet_voltage").state == "121.7"
    assert hass.states.get("sensor.garage_4_outlet_power").state == "0.0"
    total = hass.states.get("sensor.garage_4_outlet_energy_total")
    assert total.state == "104.127"
    assert total.attributes["state_class"] == "total_increasing"

    event = hass.states.get("event.garage_4_outlet_button_1")
    assert event.attributes["event_types"] == ["single", "double", "triple", "hold"]
    assert hass.states.get("event.garage_4_outlet_button_2") is None
    assert hass.states.get("button.garage_4_outlet_restart") is not None

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, strip_entry.entry_id)
    assert not [e for e in entities if e.domain in ("light", "select", "number", "cover")]
    presses = sorted(e.entity_id for e in entities if e.domain == "button" and "button_1" in e.entity_id)
    assert presses == [
        "button.garage_4_outlet_button_1_double_press",
        "button.garage_4_outlet_button_1_hold",
        "button.garage_4_outlet_button_1_single_press",
        "button.garage_4_outlet_button_1_triple_press",
    ]
    assert all(registry.async_get(p).disabled_by is er.RegistryEntryDisabler.INTEGRATION for p in presses)

    assert await hass.config_entries.async_unload(strip_entry.entry_id)


async def test_plug3_switch(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, strip_entry: MockConfigEntry
) -> None:
    """Each outlet switch posts its own number to /api/outlet."""
    mock_strip(aioclient_mock)
    await setup_entry(hass, strip_entry)

    mock_strip(aioclient_mock, make_strip(states=("on", "off", "on"), power=60.0))
    await hass.services.async_call("switch", "turn_on", {ATTR_ENTITY_ID: OUTLET_3}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", STRIP_BASE) == [{"outlet": 3, "state": "on"}]
    assert hass.states.get(OUTLET_3).state == STATE_ON
    assert hass.states.get("sensor.garage_4_outlet_power").state == "60.0"

    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: OUTLET_2}, blocking=True)
    await hass.services.async_call("switch", "toggle", {ATTR_ENTITY_ID: OUTLET_1}, blocking=True)
    assert posted(aioclient_mock, "/api/outlet", STRIP_BASE)[-2:] == [
        {"outlet": 2, "state": "off"},
        {"outlet": 1, "state": "toggle"},
    ]


async def test_plug3_button_press(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, strip_entry: MockConfigEntry
) -> None:
    """The press buttons send the action to /api/controller/press."""
    mock_strip(aioclient_mock)
    await setup_entry(hass, strip_entry)
    registry = er.async_get(hass)
    for action in ("triple_press", "hold"):
        registry.async_update_entity(f"button.garage_4_outlet_button_1_{action}", disabled_by=None)
    await hass.config_entries.async_reload(strip_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.garage_4_outlet_button_1_triple_press"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.garage_4_outlet_button_1_hold"}, blocking=True
    )
    assert posted(aioclient_mock, "/api/controller/press", STRIP_BASE) == [
        {"button": 1, "presses": "triple"},
        {"button": 1, "presses": "hold"},
    ]


async def test_plug3_button_event(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, strip_entry: MockConfigEntry
) -> None:
    """A physical double press, seen on a poll, fires button 1 double."""
    mock_strip(aioclient_mock)
    await setup_entry(hass, strip_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)

    mock_strip(aioclient_mock, make_strip(states=("on", "on", "off"), count=1, last="double"))
    await strip_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "double")]
    assert hass.states.get(OUTLET_2).state == STATE_ON


async def test_plug3_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    strip_entry: MockConfigEntry,
) -> None:
    """The device's MQTT state topic updates the switches; actions arrive on their own topic."""
    info = copy.deepcopy(STRIP_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": STRIP_TOPIC}
    mock_strip(aioclient_mock, info=info)
    await setup_entry(hass, strip_entry)
    assert strip_entry.runtime_data.mqtt_topic == STRIP_TOPIC

    state = make_strip(states=("off", "off", "on"), power=60.0)
    del state["uptimeMs"]
    del state["buttons"][0]["lastActionMsAgo"]
    async_fire_mqtt_message(hass, f"{STRIP_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert hass.states.get(OUTLET_1).state == STATE_OFF
    assert hass.states.get(OUTLET_3).state == STATE_ON
    assert hass.states.get("sensor.garage_4_outlet_power").state == "60.0"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{STRIP_TOPIC}/button/1/action", "hold")
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(1, "hold")]


@pytest.mark.parametrize(
    ("name", "title"),
    [("Garage 4 Outlet", "Garage 4 Outlet"), ("Logix Plug 3", "Logix Plug 3 0420")],
)
async def test_plug3_zeroconf(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, name: str, title: str
) -> None:
    """A discovered strip is titled with its own name, or the model name plus ID if it has none."""
    info = copy.deepcopy(STRIP_INFO)
    info["name"] = name
    mock_strip(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_ZEROCONF},
        data=ZeroconfServiceInfo(
            ip_address=ip_address(STRIP_HOST),
            ip_addresses=[ip_address(STRIP_HOST)],
            hostname="garage-4-outlet.local.",
            name="garage-4-outlet._logix._tcp.local.",
            port=80,
            type="_logix._tcp.local.",
            properties={"id": STRIP_ID, "model": "logixplug3", "fw": "1.0.0", "api": "1", "name": name},
        ),
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == title
    assert result["data"] == {CONF_HOST: STRIP_HOST}
