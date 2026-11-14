"""Logix Temp tests."""

from __future__ import annotations

import copy
from datetime import timedelta
import json
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_mqtt_message
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import MqttMockHAClient

from custom_components.logixdiy.const import CONF_SCAN_INTERVAL, DOMAIN

from .conftest import posted, setup_entry

TEMP_HOST = "192.168.22.130"
TEMP_BASE = f"http://{TEMP_HOST}"
TEMP_ID = "2cf4327737ce"
TEMP_TOPIC = f"logixtemp/{TEMP_ID}"

TEMPERATURE = "sensor.garage_temperature"
PROBE_2 = "sensor.garage_temperature_temperature_2"
READ_NOW = "button.garage_temperature_read_now"
ADDRESS = "28b7a79304000009"

# Shapes from the Logix Temp firmware 1.0.0 API reference (D1 mini + DS18B20 on D3).
TEMP_INFO: dict[str, Any] = {
    "manufacturer": "Logix",
    "model": "logixtemp",
    "name": "Garage Temperature",
    "id": TEMP_ID,
    "mac": "2C:F4:32:77:37:CE",
    "hostname": "garage-temperature",
    "ip": TEMP_HOST,
    "fw": "1.0.0",
    "api": 1,
    "authRequired": False,
    "capabilities": {
        "outlets": 0,
        "buttons": 0,
        "outletKeys": [],
        "outletNames": [],
        "actions": [],
        "temperature": True,
        "sensors": 1,
        "sensorKeys": ["temp"],
        "sensorNames": ["Garage Temperature"],
        "energy": False,
        "energyMeters": 0,
    },
    "mqtt": {"enabled": False, "connected": False, "topic": TEMP_TOPIC},
}

TEMP_STATUS: dict[str, Any] = {
    "title": "Logix Temp",
    "name": "Garage Temperature",
    "version": "1.0.0",
    "mode": "station",
    "savedSsid": "ESP",
    "connected": True,
    "ip": TEMP_HOST,
    "rssi": -61,
    "hostname": "garage-temperature",
    "mac": "2C:F4:32:77:37:CE",
    "uptime": 81,
    "heap": 30120,
    "chip": "ESP8266EX",
    "authEnabled": False,
    "mqttConnected": False,
    "sensorPin": "D3 (GPIO0)",
    "sensorCount": 1,
    "busSearches": 1,
}


def probe(
    n: int = 1, celsius: float | None = 22.81, online: bool | None = None, live: bool = True
) -> dict[str, Any]:
    """One entry of "sensors" in GET /api/controller (live) or the MQTT state topic."""
    online = celsius is not None if online is None else online
    entry: dict[str, Any] = {
        "sensor": n,
        "key": "temp" if n == 1 else f"temp{n}",
        "name": "Garage Temperature" if n == 1 else f"Garage Temperature {n}",
        "address": ADDRESS if n == 1 else f"28ff00000000000{n}",
        "online": online,
        "temperatureC": celsius if online else None,
        "temperatureF": round(celsius * 1.8 + 32, 2) if online and celsius is not None else None,
        "minC": 22.5,
        "maxC": 23.0,
    }
    if live:
        entry |= {"readCount": 8, "errorCount": 0, "lastReadMsAgo": 3120}
    return entry


def make_temp(*probes: dict[str, Any], live: bool = True) -> dict[str, Any]:
    """Build a Logix Temp GET /api/controller response."""
    state: dict[str, Any] = {
        "name": "Garage Temperature",
        "unit": "F",
        "offsetC": 0,
        "intervalS": 10,
        "sensors": list(probes) if probes else [probe(live=live)],
    }
    if live:
        state = {"uptimeMs": 81234, **state}
    return state


OK = {"ok": True, "message": "Reading now.", "restart": False}


def mock_temp(
    aioclient_mock: AiohttpClientMocker,
    controller: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
) -> None:
    """Register every endpoint of a healthy Logix Temp."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{TEMP_BASE}/api/info", json=info or TEMP_INFO)
    aioclient_mock.get(f"{TEMP_BASE}/api/controller", json=controller or make_temp())
    aioclient_mock.get(f"{TEMP_BASE}/api/status", json=TEMP_STATUS)
    for path in ("/api/controller/read", "/api/reboot"):
        aioclient_mock.post(f"{TEMP_BASE}{path}", json=OK)


@pytest.fixture
def temp_entry() -> MockConfigEntry:
    """A config entry for the test Logix Temp."""
    return MockConfigEntry(
        domain=DOMAIN, unique_id=TEMP_ID, title="Garage Temperature", data={CONF_HOST: TEMP_HOST}
    )


async def test_temp_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, temp_entry: MockConfigEntry
) -> None:
    """One temperature sensor named after the device, a read-now and a restart button; nothing else."""
    mock_temp(aioclient_mock)
    await setup_entry(hass, temp_entry)
    assert temp_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(temp_entry.runtime_data.device_id)
    assert device.model == "Logix Temp"
    assert device.model_id == "logixtemp"

    temperature = hass.states.get(TEMPERATURE)
    assert float(temperature.state) == 22.81
    assert temperature.attributes["friendly_name"] == "Garage Temperature"
    assert temperature.attributes["device_class"] == "temperature"
    assert temperature.attributes["unit_of_measurement"] == "°C"
    assert temperature.attributes["state_class"] == "measurement"
    assert temperature.attributes["address"] == ADDRESS
    assert temperature.attributes["min_celsius"] == 22.5
    assert temperature.attributes["max_celsius"] == 23.0

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, temp_entry.entry_id)
    assert registry.async_get(TEMPERATURE).unique_id == f"{TEMP_ID}_temperature"
    assert not [e for e in entities if e.domain in ("switch", "event", "light", "select", "number", "cover")]
    assert sorted(e.entity_id for e in entities if e.domain == "button") == [
        READ_NOW,
        "button.garage_temperature_restart",
    ]
    assert sorted(e.entity_id for e in entities if e.domain == "sensor") == [
        TEMPERATURE,
        "sensor.garage_temperature_ip_address",
        "sensor.garage_temperature_wi_fi_signal",
    ]

    # No buttons, so no press triggers; and polling without MQTT is relaxed to 10 s.
    assert temp_entry.runtime_data.update_interval == timedelta(seconds=10)

    assert await hass.config_entries.async_unload(temp_entry.entry_id)


async def test_temp_scan_interval_option(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A poll interval set under Configure wins over the model's default."""
    mock_temp(aioclient_mock)
    temp_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEMP_ID,
        title="Garage Temperature",
        data={CONF_HOST: TEMP_HOST},
        options={CONF_SCAN_INTERVAL: 2.5},
    )
    await setup_entry(hass, temp_entry)
    assert temp_entry.runtime_data.update_interval == timedelta(seconds=2.5)


async def test_temp_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, temp_entry: MockConfigEntry
) -> None:
    """The sensor is unavailable while the probe isn't answering, or is missing from the bus."""
    mock_temp(aioclient_mock, make_temp(probe(celsius=None)))
    await setup_entry(hass, temp_entry)
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE

    mock_temp(aioclient_mock, make_temp(probe(celsius=21.06)))
    await temp_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(TEMPERATURE).state) == 21.06

    controller = make_temp()
    controller["sensors"] = []
    mock_temp(aioclient_mock, controller)
    await temp_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE


async def test_temp_no_probe_at_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, temp_entry: MockConfigEntry
) -> None:
    """With no probe found yet, the sensor still exists (unavailable) and fills in later."""
    info = copy.deepcopy(TEMP_INFO)
    info["capabilities"] |= {"sensors": 0, "sensorKeys": [], "sensorNames": []}
    controller = make_temp()
    controller["sensors"] = []
    mock_temp(aioclient_mock, controller, info)
    await setup_entry(hass, temp_entry)
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE

    mock_temp(aioclient_mock, make_temp(), info)
    await temp_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(TEMPERATURE).state) == 22.81


async def test_temp_second_probe(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, temp_entry: MockConfigEntry
) -> None:
    """A second DS18B20 on the bus gets its own "Temperature 2" sensor."""
    info = copy.deepcopy(TEMP_INFO)
    info["capabilities"] |= {
        "sensors": 2,
        "sensorKeys": ["temp", "temp2"],
        "sensorNames": ["Garage Temperature", "Garage Temperature 2"],
    }
    mock_temp(aioclient_mock, make_temp(probe(1), probe(2, celsius=4.5)), info)
    await setup_entry(hass, temp_entry)

    second = hass.states.get(PROBE_2)
    assert float(second.state) == 4.5
    assert second.attributes["friendly_name"] == "Garage Temperature Temperature 2"
    assert second.attributes["address"] == "28ff000000000002"
    assert er.async_get(hass).async_get(PROBE_2).unique_id == f"{TEMP_ID}_temperature_2"
    assert float(hass.states.get(TEMPERATURE).state) == 22.81


async def test_temp_read_now(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, temp_entry: MockConfigEntry
) -> None:
    """The read-now button posts to /api/controller/read."""
    mock_temp(aioclient_mock)
    await setup_entry(hass, temp_entry)

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: READ_NOW}, blocking=True)
    assert posted(aioclient_mock, "/api/controller/read", TEMP_BASE) == [None]
    assert posted(aioclient_mock, "/api/reboot", TEMP_BASE) == []


async def test_temp_mqtt(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    temp_entry: MockConfigEntry,
) -> None:
    """The MQTT state topic (without the live counters) updates the temperature."""
    info = copy.deepcopy(TEMP_INFO)
    info["mqtt"] = {"enabled": True, "connected": True, "topic": TEMP_TOPIC}
    mock_temp(aioclient_mock, info=info)
    await setup_entry(hass, temp_entry)
    assert temp_entry.runtime_data.mqtt_topic == TEMP_TOPIC

    state = make_temp(probe(celsius=24.13, live=False), live=False)
    async_fire_mqtt_message(hass, f"{TEMP_TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    assert float(hass.states.get(TEMPERATURE).state) == 24.13
    assert temp_entry.runtime_data.push_active

    offline = make_temp(probe(celsius=24.13, online=False, live=False), live=False)
    async_fire_mqtt_message(hass, f"{TEMP_TOPIC}/state", json.dumps(offline))
    await hass.async_block_till_done()
    assert hass.states.get(TEMPERATURE).state == STATE_UNAVAILABLE
