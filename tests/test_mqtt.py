"""MQTT push tests."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.light import ATTR_EFFECT
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_mqtt_message,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import MqttMockHAClient

from custom_components.logixdiy.const import EVENT_BUTTON_ACTION, PUSH_SCAN_INTERVAL

from .conftest import TOPIC, make_controller, mock_device, posted, setup_entry


async def test_mqtt_push(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    info: dict[str, Any],
) -> None:
    """State and actions arrive over MQTT; polling slows down while they do."""
    info["mqtt"] = {"enabled": True, "connected": True, "topic": TOPIC}
    mock_device(aioclient_mock, info=info)
    await setup_entry(hass, config_entry)
    coordinator = config_entry.runtime_data
    assert coordinator.mqtt_topic == TOPIC
    assert not coordinator.push_active

    async_fire_mqtt_message(hass, f"{TOPIC}/status", "online")
    await hass.async_block_till_done()
    assert coordinator.push_active
    assert coordinator.update_interval == PUSH_SCAN_INTERVAL

    state = make_controller(
        states=("triple", "off", "off"), counts=(1, 0, 0), last=("triple", "none", "none")
    )
    del state["uptimeMs"]
    async_fire_mqtt_message(hass, f"{TOPIC}/state", json.dumps(state))
    await hass.async_block_till_done()
    led1 = hass.states.get("light.logix_3_e527_led_1")
    assert led1.state == STATE_ON
    assert led1.attributes[ATTR_EFFECT] == "triple"

    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    async_fire_mqtt_message(hass, f"{TOPIC}/button/2/action", "double")
    async_fire_mqtt_message(hass, f"{TOPIC}/button/9/action", "double")  # no such button
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(2, "double")]
    assert hass.states.get("event.logix_3_e527_button_2").attributes["event_type"] == "double"

    # Commands still go over HTTP, without an extra poll while MQTT reports the result.
    calls = len(aioclient_mock.mock_calls)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.logix_3_e527_led_1_state", "option": "off"},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {"led1State": "off"}
    assert len(aioclient_mock.mock_calls) == calls + 1

    # A poll while pushing moves the action baseline without firing again.
    mock_device(
        aioclient_mock,
        info=info,
        controller=make_controller(counts=(1, 1, 0), last=("triple", "double", "none")),
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1

    async_fire_mqtt_message(hass, f"{TOPIC}/status", "offline")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not coordinator.push_active
    assert coordinator.update_interval.total_seconds() == 1


async def test_mqtt_disabled_in_options(
    hass: HomeAssistant,
    mqtt_mock: MqttMockHAClient,
    aioclient_mock: AiohttpClientMocker,
    info: dict[str, Any],
) -> None:
    """With MQTT turned off in options, the integration only polls."""
    info["mqtt"] = {"enabled": True, "connected": True, "topic": TOPIC}
    mock_device(aioclient_mock, info=info)
    entry = MockConfigEntry(
        domain="logixdiy", unique_id=info["id"], data={"host": info["ip"]}, options={"use_mqtt": False}
    )
    await setup_entry(hass, entry)
    assert entry.runtime_data.mqtt_topic is None
