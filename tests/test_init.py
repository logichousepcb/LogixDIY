"""Setup, entity and polling tests."""

from __future__ import annotations

from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.light import ATTR_EFFECT, ATTR_RGB_COLOR
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_get_device_automations,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.logixdiy.const import DOMAIN, EVENT_BUTTON_ACTION

from .conftest import BASE, DEVICE_ID, make_controller, mock_device, posted, setup_entry


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """The device, its entities and their states are created."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(config_entry.runtime_data.device_id)
    assert device is not None
    assert device.identifiers == {(DOMAIN, DEVICE_ID)}
    assert device.model == "Logix 3"
    assert device.model_id == "logix3"
    assert device.sw_version == "1.2.0"

    assert hass.states.get("light.logix_3_e527_led_1").state == STATE_OFF
    led2 = hass.states.get("light.logix_3_e527_led_2")
    assert led2.state == STATE_ON
    assert led2.attributes[ATTR_EFFECT] == "double"
    assert led2.attributes[ATTR_RGB_COLOR] == (255, 160, 0)
    assert hass.states.get("select.logix_3_e527_led_2_state").state == "double"
    assert hass.states.get("number.logix_3_e527_led_brightness").state == "100"
    assert hass.states.get("sensor.logix_3_e527_wi_fi_signal").state == "-58"
    assert hass.states.get("event.logix_3_e527_button_3") is not None

    registry = er.async_get(hass)
    press = registry.async_get("button.logix_3_e527_button_1_double_press")
    assert press is not None and press.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """An unreachable device is retried later."""
    aioclient_mock.get(f"{BASE}/api/info", exc=TimeoutError)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A 401 while polling asks the user for the new password."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/api/controller", status=401)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_polling_fires_actions(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """A new actionCount fires the event entity and the bus event, once."""
    mock_device(aioclient_mock, controller=make_controller(counts=(2, 0, 0), last=("single", "none", "none")))
    await setup_entry(hass, config_entry)
    events = async_capture_events(hass, EVENT_BUTTON_ACTION)
    coordinator = config_entry.runtime_data

    mock_device(aioclient_mock, controller=make_controller(counts=(2, 0, 1), last=("single", "none", "hold")))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data == {"device_id": coordinator.device_id, "button": 3, "action": "hold"}
    assert hass.states.get("event.logix_3_e527_button_3").attributes["event_type"] == "hold"

    # Same counts again: nothing new.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(events) == 1

    # The device restarted (counts reset) and button 1 was pressed since.
    mock_device(aioclient_mock, controller=make_controller(counts=(1, 0, 0), last=("double", "none", "none")))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [(e.data["button"], e.data["action"]) for e in events] == [(3, "hold"), (1, "double")]


async def test_light_commands(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Light, select, number and button services send the right API calls."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)

    await hass.services.async_call(
        "light",
        "turn_on",
        {
            ATTR_ENTITY_ID: "light.logix_3_e527_led_1",
            "effect": "hold",
            "rgb_color": (1, 2, 3),
            "brightness": 128,
        },
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {
        "led1State": "hold",
        "led1Color4": "#010203",
        "brightness": 128,
    }

    # Color change on an LED that is on edits the slot it is showing.
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: "light.logix_3_e527_led_2", "rgb_color": (0, 255, 0)},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {"led2State": "double", "led2Color2": "#00ff00"}

    await hass.services.async_call(
        "light", "turn_off", {ATTR_ENTITY_ID: "light.logix_3_e527_led_2"}, blocking=True
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {"led2State": "off"}

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.logix_3_e527_led_3_state", "option": "triple"},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {"led3State": "triple"}

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.logix_3_e527_led_brightness", "value": 50},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller/brightness")[-1] == {"brightness": 128}

    await hass.services.async_call(
        DOMAIN,
        "set_led_colors",
        {ATTR_ENTITY_ID: "light.logix_3_e527_led_3", "single_color": [255, 0, 0], "off_color": [0, 0, 16]},
        blocking=True,
    )
    assert posted(aioclient_mock, "/api/controller")[-1] == {
        "led3Color1": "#ff0000",
        "led3OffColor": "#000010",
    }

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.logix_3_e527_restart"}, blocking=True
    )
    assert len(posted(aioclient_mock, "/api/reboot")) == 1


async def test_simulated_press(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Enabled press buttons call the press endpoint."""
    mock_device(aioclient_mock)
    config_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "button",
        DOMAIN,
        f"{DEVICE_ID}_button_2_hold",
        config_entry=config_entry,
        suggested_object_id="logix_3_e527_button_2_hold",
    )
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.logix_3_e527_button_2_hold"}, blocking=True
    )
    assert posted(aioclient_mock, "/api/controller/press")[-1] == {"button": 2, "presses": "hold"}


async def test_device_triggers(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Every button and action is offered as a device trigger."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)
    device_id = config_entry.runtime_data.device_id

    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device_id)
    ours = {(t["subtype"], t["type"]) for t in triggers if t["domain"] == DOMAIN}
    assert len(ours) == 12
    assert ("button_2", "double") in ours

    # An automation using the trigger runs when the button is double pressed.
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "triggers": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": device_id,
                    "type": "double",
                    "subtype": "button_2",
                },
                "actions": {"event": "test_fired"},
            }
        },
    )
    fired = async_capture_events(hass, "test_fired")
    mock_device(aioclient_mock, controller=make_controller(counts=(0, 1, 0), last=("none", "single", "none")))
    await config_entry.runtime_data.async_refresh()
    mock_device(aioclient_mock, controller=make_controller(counts=(0, 2, 0), last=("none", "double", "none")))
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(fired) == 1
