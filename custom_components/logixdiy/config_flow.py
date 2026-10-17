"""Config flow for LogixDIY: manual entry, zeroconf and MQTT discovery."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import LogixAuthError, LogixClient, LogixConnectionError, LogixError
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_USE_MQTT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_MQTT,
    DOMAIN,
    LOGGER,
)
from .coordinator import LogixConfigEntry
from .models import device_title, unsupported_reason

PASSWORD_SCHEMA = vol.Schema(
    {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class LogixConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Logix device."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._host = ""
        self._info: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: LogixConfigEntry) -> LogixOptionsFlow:
        """Return the options flow."""
        return LogixOptionsFlow()

    def _client(self, host: str, password: str | None = None) -> LogixClient:
        return LogixClient(async_get_clientsession(self.hass), host, password)

    # Manual setup ------------------------------------------------------------------------------

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Set up a device by host name or IP address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await self._client(host).get_info()
            except LogixConnectionError:
                errors["base"] = "cannot_connect"
            except LogixError:
                LOGGER.exception("Unexpected error reading %s", host)
                errors["base"] = "unknown"
            else:
                if reason := unsupported_reason(info):
                    return self.async_abort(reason=reason)
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                self._host, self._info = host, info
                return await self._async_step_credentials_or_create()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}), user_input
            ),
            errors=errors,
        )

    # Discovery ---------------------------------------------------------------------------------

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Handle a device found by its _logix._tcp mDNS advertisement."""
        if discovery_info.ip_address.version != 4:
            return self.async_abort(reason="not_ipv4_address")
        properties = discovery_info.properties
        return await self._async_step_discovered(
            discovery_info.host, properties.get("id"), properties.get("model")
        )

    async def async_step_mqtt(self, discovery_info: MqttServiceInfo) -> ConfigFlowResult:
        """Handle a device's retained message on logix/discovery/<id>."""
        try:
            payload = json.loads(discovery_info.payload)
        except ValueError:
            return self.async_abort(reason="invalid_discovery_info")
        if not isinstance(payload, dict):
            return self.async_abort(reason="invalid_discovery_info")
        return await self._async_step_discovered(payload.get("ip"), payload.get("id"), payload.get("model"))

    async def _async_step_discovered(
        self, host: str | None, device_id: str | None, model: str | None
    ) -> ConfigFlowResult:
        if not host or not device_id:
            return self.async_abort(reason="invalid_discovery_info")
        if unsupported_reason({"model": model}):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        try:
            info = await self._client(host).get_info()
        except LogixError:
            return self.async_abort(reason="cannot_connect")
        if info["id"] != device_id:
            return self.async_abort(reason="invalid_discovery_info")
        if reason := unsupported_reason(info):
            return self.async_abort(reason=reason)

        self._host, self._info = host, info
        self.context["title_placeholders"] = {"name": device_title(info)}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding a discovered device."""
        if user_input is not None:
            return await self._async_step_credentials_or_create()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"name": device_title(self._info), "host": self._host},
        )

    # Credentials -------------------------------------------------------------------------------

    async def _async_step_credentials_or_create(self) -> ConfigFlowResult:
        if self._info.get("authRequired"):
            return await self.async_step_credentials()
        return self.async_create_entry(title=device_title(self._info), data={CONF_HOST: self._host})

    async def _async_check_password(self, host: str, password: str) -> str | None:
        """Return an error key, or None if the password works."""
        try:
            await self._client(host, password).get_controller()
        except LogixAuthError:
            return "invalid_auth"
        except LogixConnectionError:
            return "cannot_connect"
        except LogixError:
            LOGGER.exception("Unexpected error checking the password on %s", host)
            return "unknown"
        return None

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the admin password of a protected device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            if not (error := await self._async_check_password(self._host, password)):
                return self.async_create_entry(
                    title=device_title(self._info),
                    data={CONF_HOST: self._host, CONF_PASSWORD: password},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="credentials",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": device_title(self._info)},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The device's admin password changed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the new admin password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            if not (error := await self._async_check_password(entry.data[CONF_HOST], password)):
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: password})
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    # Reconfigure -------------------------------------------------------------------------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the host of an existing device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await self._client(host).get_info()
            except LogixConnectionError:
                errors["base"] = "cannot_connect"
            except LogixError:
                LOGGER.exception("Unexpected error reading %s", host)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["id"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_HOST): str}), user_input or entry.data
            ),
            errors=errors,
        )


class LogixOptionsFlow(OptionsFlow):
    """Transport and polling options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_USE_MQTT, default=DEFAULT_USE_MQTT): bool,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=0.5,
                        max=60,
                        step=0.5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, self.config_entry.options),
        )
