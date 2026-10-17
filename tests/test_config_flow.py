"""Config flow tests."""

from __future__ import annotations

from ipaddress import ip_address
import json
from typing import Any

from homeassistant.config_entries import SOURCE_MQTT, SOURCE_USER, SOURCE_ZEROCONF
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.logixdiy.const import CONF_SCAN_INTERVAL, CONF_USE_MQTT, DOMAIN

from .conftest import BASE, DEVICE_ID, HOST, INFO, mock_device, setup_entry


def zeroconf_info(host: str = HOST, model: str = "logix3") -> ZeroconfServiceInfo:
    """A _logix._tcp advertisement."""
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        hostname="esp12f-e527.local.",
        name="esp12f-e527._logix._tcp.local.",
        port=80,
        type="_logix._tcp.local.",
        properties={"model": model, "id": DEVICE_ID, "fw": "1.2.0", "api": "1", "manufacturer": "Logix"},
    )


async def test_user_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Manual setup of an open device creates the entry."""
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: f" {HOST} "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Logix 3 E527"
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == DEVICE_ID


async def test_user_flow_cannot_connect(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A connection failure shows an error, and the user can retry."""
    aioclient_mock.get(f"{BASE}/api/info", exc=TimeoutError)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_password(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, info: dict[str, Any]
) -> None:
    """A protected device asks for the password and checks it."""
    info["authRequired"] = True
    aioclient_mock.get(f"{BASE}/api/info", json=info)
    aioclient_mock.get(f"{BASE}/api/controller", status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    mock_device(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "secret"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_PASSWORD: "secret"}
    _, _, _, headers = aioclient_mock.mock_calls[-1]
    assert headers["Authorization"] == "Basic YWRtaW46c2VjcmV0"  # admin:secret


async def test_user_flow_unsupported(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, info: dict[str, Any]
) -> None:
    """Unknown models and newer API versions are refused."""
    info["model"] = "logix9"
    mock_device(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"

    info["model"], info["api"] = "logix3", 2
    mock_device(aioclient_mock, info=info)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["reason"] == "api_too_new"


async def test_zeroconf_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A discovered device is confirmed and added."""
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST}


async def test_zeroconf_updates_host(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Rediscovery at a new address updates the existing entry."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info(host="192.168.22.240")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.22.240"


async def test_zeroconf_unsupported_model(hass: HomeAssistant) -> None:
    """Unknown models are ignored without contacting the device."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=zeroconf_info(model="toaster")
    )
    assert result["reason"] == "not_supported"


async def test_mqtt_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """The retained logix/discovery message starts setup."""
    mock_device(aioclient_mock)
    discovery = MqttServiceInfo(
        topic=f"logix/discovery/{DEVICE_ID}",
        payload=json.dumps(INFO),
        qos=0,
        retain=True,
        subscribed_topic="logix/discovery/#",
        timestamp=0,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_MQTT}, data=discovery
    )
    assert result["step_id"] == "discovery_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    bad = MqttServiceInfo(
        topic="logix/discovery/x",
        payload="",
        qos=0,
        retain=True,
        subscribed_topic="logix/discovery/#",
        timestamp=0,
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_MQTT}, data=bad)
    assert result["reason"] == "invalid_discovery_info"


async def test_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Reauth stores the new password."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new"


async def test_reconfigure_wrong_device(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    info: dict[str, Any],
) -> None:
    """Reconfigure refuses an address that belongs to another device."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)

    info["id"] = "aabbccddeeff"
    aioclient_mock.get("http://10.0.0.9/api/info", json=info)
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "10.0.0.9"})
    assert result["reason"] == "wrong_device"
    assert config_entry.data[CONF_HOST] == HOST


async def test_options(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, config_entry: MockConfigEntry
) -> None:
    """Options are saved and applied on reload."""
    mock_device(aioclient_mock)
    await setup_entry(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_USE_MQTT: False, CONF_SCAN_INTERVAL: 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.runtime_data.update_interval.total_seconds() == 5
