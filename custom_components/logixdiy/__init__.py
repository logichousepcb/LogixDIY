"""The LogixDIY integration: Logix devices on the local network."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import LogixClient, LogixError
from .const import DOMAIN, MANUFACTURER
from .coordinator import LogixConfigEntry, LogixCoordinator
from .models import MODELS, unsupported_reason


async def async_setup_entry(hass: HomeAssistant, entry: LogixConfigEntry) -> bool:
    """Set up a Logix device from a config entry."""
    client = LogixClient(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data.get(CONF_PASSWORD))
    try:
        info = await client.get_info()
    except LogixError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    if info["id"] != entry.unique_id:
        # The address now belongs to another device; wait for discovery to report the new one.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="wrong_device",
            translation_placeholders={"host": client.host},
        )
    if reason := unsupported_reason(info):
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key=reason)

    coordinator = LogixCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, info["id"])},
        connections={(dr.CONNECTION_NETWORK_MAC, info["mac"])} if info.get("mac") else set(),
        manufacturer=info.get("manufacturer", MANUFACTURER),
        model=coordinator.model.name,
        model_id=info["model"],
        name=entry.title,
        sw_version=info.get("fw"),
        configuration_url=client.base_url,
    )
    coordinator.device_id = device.id
    entry.runtime_data = coordinator

    # MQTT can take a while to connect; don't hold up setup for it.
    entry.async_create_background_task(
        hass, coordinator.async_setup_push(), f"{DOMAIN} MQTT subscribe {info['id']}"
    )

    await hass.config_entries.async_forward_entry_setups(entry, MODELS[info["model"]].platforms)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LogixConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, entry.runtime_data.model.platforms)


async def _async_options_updated(hass: HomeAssistant, entry: LogixConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
