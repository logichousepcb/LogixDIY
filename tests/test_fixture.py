"""Logix Fixture tests."""

from __future__ import annotations

import copy
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
)
from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_PASSWORD, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.logixdiy.const import DOMAIN

from .conftest import posted, setup_entry

FIX_HOST = "192.168.22.42"
FIX_BASE = f"http://{FIX_HOST}"
FIX_ID = "48e72971f314"

LIGHT = "light.molly_s_tree"
SPEED = "number.molly_s_tree_effect_speed"
IDENTIFY = "button.molly_s_tree_identify"

# Copied from a Logix Fixture running logix-fixture-firmware 1.2.0 (47 LEDs on GPIO2).
FIX_INFO: dict[str, Any] = {
    "id": FIX_ID,
    "name": "Molly's Tree",
    "model": "logixfixture",
    "manufacturer": "Logix",
    "firmware": "LoGiX Fixture",
    "version": "1.2.0",
    "api": 1,
    "auth": False,
    "wsPort": 81,
    "hostname": "molly-s-tree",
    "build": "Nov 22 2026 07:43:06",
    "mac": "48:E7:29:71:F3:14",
    "chipId": "71F314",
    "capabilities": {
        "rgb": True,
        "white": False,
        "effects": 10,
        "speed": True,
        "ir": True,
        "identify": True,
        "websocket": True,
        "maxLeds": 800,
        "ota": True,
    },
    "wifi": {
        "mode": "sta",
        "ssid": "ESP",
        "status": "connected",
        "connected": True,
        "ip": FIX_HOST,
        "rssi": -61,
        "apActive": False,
    },
    "leds": {
        "pin": 2,
        "count": 47,
        "colorOrder": "GRB",
        "estimatedMa": 500,
        "maxMa": 500,
        "powerLimited": True,
    },
    "ir": {"pin": 4, "enabled": True},
    "system": {
        "uptimeS": 2788,
        "freeHeap": 33640,
        "sketchSize": 454912,
        "freeSketchSpace": 1638400,
        "flashSize": 4194304,
        "resetReason": "External System",
    },
}

# What /api/info returns without the token while the API token is on.
FIX_PUBLIC_INFO: dict[str, Any] = {
    key: FIX_INFO[key]
    for key in ("id", "name", "model", "manufacturer", "firmware", "version", "api", "wsPort")
} | {"auth": True}

EFFECT_NAMES = [
    "Solid",
    "Breathe",
    "Rainbow",
    "Rainbow Cycle",
    "Color Wipe",
    "Theater Chase",
    "Twinkle",
    "Comet",
    "Candle",
    "Christmas",
]
EFFECTS = [{"id": i, "name": name} for i, name in enumerate(EFFECT_NAMES)]


def make_state(
    on: bool = True,
    bri: int = 128,
    color: tuple[int, int, int] = (255, 17, 100),
    effect: int = 9,
    speed: int = 128,
) -> dict[str, Any]:
    """Build a GET /api/state response."""
    return {
        "on": on,
        "bri": bri,
        "color": list(color),
        "hex": "#{:02x}{:02x}{:02x}".format(*color),
        "effect": effect,
        "effectName": EFFECT_NAMES[effect],
        "speed": speed,
    }


def mock_fixture(
    aioclient_mock: AiohttpClientMocker,
    state: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
    effects_fail: bool = False,
) -> None:
    """Register every endpoint of a healthy Logix Fixture."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{FIX_BASE}/api/info", json=info or FIX_INFO)
    aioclient_mock.get(f"{FIX_BASE}/api/state", json=state or make_state())
    if not effects_fail:
        aioclient_mock.get(f"{FIX_BASE}/api/effects", json=EFFECTS)
    else:
        aioclient_mock.get(f"{FIX_BASE}/api/effects", status=500, json={"ok": False, "error": "boom"})
    aioclient_mock.post(f"{FIX_BASE}/api/state", json=state or make_state())
    for path in ("/api/identify", "/api/reboot"):
        aioclient_mock.post(f"{FIX_BASE}{path}", json={"ok": True})


@pytest.fixture
def fix_entry() -> MockConfigEntry:
    """A config entry for the test Logix Fixture."""
    return MockConfigEntry(domain=DOMAIN, unique_id=FIX_ID, title="Molly's Tree", data={CONF_HOST: FIX_HOST})


async def test_fixture_setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, fix_entry: MockConfigEntry
) -> None:
    """One light named after the device, an effect speed, identify and restart, and diagnostics."""
    mock_fixture(aioclient_mock)
    await setup_entry(hass, fix_entry)
    assert fix_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get(fix_entry.runtime_data.device_id)
    assert device.model == "Logix Fixture"
    assert device.model_id == "logixfixture"
    assert device.sw_version == "1.2.0"  # /api/info "version"
    assert device.manufacturer == "Logix"

    light = hass.states.get(LIGHT)
    assert light.state == STATE_ON
    assert light.attributes["friendly_name"] == "Molly's Tree"
    assert light.attributes[ATTR_BRIGHTNESS] == 128
    assert light.attributes[ATTR_RGB_COLOR] == (255, 17, 100)
    assert light.attributes[ATTR_EFFECT] == "christmas"
    assert light.attributes[ATTR_EFFECT_LIST] == [
        EFFECT_OFF,
        "breathe",
        "rainbow",
        "rainbow_cycle",
        "color_wipe",
        "theater_chase",
        "twinkle",
        "comet",
        "candle",
        "christmas",
    ]
    assert hass.states.get(SPEED).state == "50"
    assert hass.states.get("sensor.molly_s_tree_wi_fi_signal").state == "-61"

    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, fix_entry.entry_id)
    assert registry.async_get(LIGHT).unique_id == f"{FIX_ID}_light"
    assert not [e for e in entities if e.domain in ("switch", "event", "select", "cover")]
    assert [e.entity_id for e in entities if e.domain == "light"] == [LIGHT]
    assert sorted(e.entity_id for e in entities if e.domain == "button") == [
        IDENTIFY,
        "button.molly_s_tree_restart",
    ]
    assert [e.entity_id for e in entities if e.domain == "number"] == [SPEED]

    # No buttons to catch; poll for IR remote changes every 5 s.
    assert fix_entry.runtime_data.update_interval == timedelta(seconds=5)
    assert await hass.config_entries.async_unload(fix_entry.entry_id)


async def test_fixture_light_commands(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, fix_entry: MockConfigEntry
) -> None:
    """turn_on/turn_off post JSON to /api/state; "off" is the Solid effect."""
    mock_fixture(aioclient_mock)
    await setup_entry(hass, fix_entry)

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, ATTR_RGB_COLOR: (0, 160, 255), ATTR_BRIGHTNESS: 200, ATTR_EFFECT: "breathe"},
        blocking=True,
    )
    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: LIGHT, ATTR_EFFECT: EFFECT_OFF}, blocking=True
    )
    await hass.services.async_call("light", "turn_off", {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    assert posted(aioclient_mock, "/api/state", FIX_BASE) == [
        {"on": True, "color": [0, 160, 255], "bri": 200, "effect": "Breathe"},
        {"on": True, "effect": "Solid"},
        {"on": False},
    ]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "light", "turn_on", {ATTR_ENTITY_ID: LIGHT, ATTR_EFFECT: "strobe"}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "set_led_colors", {ATTR_ENTITY_ID: LIGHT, "single_color": [255, 0, 0]}, blocking=True
        )


async def test_fixture_state_updates(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, fix_entry: MockConfigEntry
) -> None:
    """A poll picks up changes made elsewhere (the IR remote, the web page)."""
    mock_fixture(aioclient_mock)
    await setup_entry(hass, fix_entry)

    mock_fixture(aioclient_mock, make_state(on=False, bri=40, color=(0, 255, 0), effect=0, speed=0))
    await fix_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    light = hass.states.get(LIGHT)
    assert light.state == STATE_OFF
    assert hass.states.get(SPEED).state == "0"

    mock_fixture(aioclient_mock, make_state(bri=40, color=(0, 255, 0), effect=0))
    await fix_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    light = hass.states.get(LIGHT)
    assert light.attributes[ATTR_EFFECT] == EFFECT_OFF
    assert light.attributes[ATTR_RGB_COLOR] == (0, 255, 0)


async def test_fixture_speed_and_identify(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, fix_entry: MockConfigEntry
) -> None:
    """The speed slider sets only the speed; identify posts to /api/identify."""
    mock_fixture(aioclient_mock)
    await setup_entry(hass, fix_entry)

    await hass.services.async_call("number", "set_value", {ATTR_ENTITY_ID: SPEED, "value": 25}, blocking=True)
    assert posted(aioclient_mock, "/api/state", FIX_BASE) == [{"speed": 64}]

    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: IDENTIFY}, blocking=True)
    assert posted(aioclient_mock, "/api/identify", FIX_BASE) == [None]
    assert posted(aioclient_mock, "/api/reboot", FIX_BASE) == []


async def test_fixture_effects_fallback(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, fix_entry: MockConfigEntry
) -> None:
    """If /api/effects fails, the light uses firmware 1.2.0's effect list."""
    mock_fixture(aioclient_mock, effects_fail=True)
    await setup_entry(hass, fix_entry)
    light = hass.states.get(LIGHT)
    assert len(light.attributes[ATTR_EFFECT_LIST]) == 10
    assert light.attributes[ATTR_EFFECT] == "christmas"


async def test_fixture_api_token_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """With the API token on, setup asks for it and sends it as X-Api-Key."""
    aioclient_mock.get(f"{FIX_BASE}/api/info", json=FIX_PUBLIC_INFO)
    aioclient_mock.get(f"{FIX_BASE}/api/state", status=401, json={"ok": False, "error": "unauthorized"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: FIX_HOST})
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    info = copy.deepcopy(FIX_INFO) | {"auth": True}
    mock_fixture(aioclient_mock, info=info)
    token = "0123456789abcdef01234567"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: token})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Molly's Tree"
    assert result["data"] == {CONF_HOST: FIX_HOST, CONF_PASSWORD: token}
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(LIGHT).state == STATE_ON
    # The password check and the setup that follows all carry the token.
    calls = aioclient_mock.mock_calls
    assert {str(url) for _, url, _, _ in calls} >= {f"{FIX_BASE}/api/state", f"{FIX_BASE}/api/effects"}
    assert all(headers["X-Api-Key"] == token for _, _, _, headers in calls)


async def test_fixture_zeroconf(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The fixture's _logix._tcp advertisement starts a discovery flow."""
    mock_fixture(aioclient_mock)
    discovery = ZeroconfServiceInfo(
        ip_address=ip_address(FIX_HOST),
        ip_addresses=[ip_address(FIX_HOST)],
        hostname="molly-s-tree.local.",
        name="molly-s-tree._logix._tcp.local.",
        port=80,
        type="_logix._tcp.local.",
        properties={
            "manufacturer": "Logix",
            "api": "1",
            "fw": "1.2.0",
            "name": "Molly's Tree",
            "id": FIX_ID,
            "model": "logixfixture",
            "ws": "81",
            "auth": "0",
        },
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=discovery
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Molly's Tree"
    assert result["data"] == {CONF_HOST: FIX_HOST}
    await hass.async_block_till_done(wait_background_tasks=True)
