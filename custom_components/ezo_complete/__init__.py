"""EZO Complete-ORP Home Assistant integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import EzoCoordinator

_LOGGER = logging.getLogger(__name__)

type EzoConfigEntry = ConfigEntry[EzoCoordinator]


SERVICE_SEND_COMMAND = "send_command"
SERVICE_FACTORY_RESET = "factory_reset"
SERVICE_EXPORT = "export_calibration"
SERVICE_IMPORT = "import_calibration"

_DEVICE_SCHEMA = {
    vol.Required(CONF_DEVICE_ID): cv.string,
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register device-targeted services once."""
    hass.data.setdefault(DOMAIN, {})

    async def _coordinator_from_call(call: ServiceCall) -> EzoCoordinator:
        device_id = call.data[CONF_DEVICE_ID]
        registry = dr.async_get(hass)
        device = registry.async_get(device_id)
        if device is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_device",
            )
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == DOMAIN:
                return entry.runtime_data
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="unknown_device",
        )

    async def handle_send_command(call: ServiceCall) -> None:
        coordinator = await _coordinator_from_call(call)
        await coordinator.async_send_raw(call.data["command"])

    async def handle_factory_reset(call: ServiceCall) -> None:
        if not call.data.get("confirm"):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="factory_not_confirmed",
            )
        coordinator = await _coordinator_from_call(call)
        await coordinator.async_factory_reset(confirm=True)

    async def handle_export(call: ServiceCall) -> None:
        coordinator = await _coordinator_from_call(call)
        await coordinator.async_export_calibration()

    async def handle_import(call: ServiceCall) -> None:
        coordinator = await _coordinator_from_call(call)
        await coordinator.async_import_calibration(call.data["payload"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        schema=vol.Schema({**_DEVICE_SCHEMA, vol.Required("command"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FACTORY_RESET,
        handle_factory_reset,
        schema=vol.Schema({**_DEVICE_SCHEMA, vol.Required("confirm"): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT,
        handle_export,
        schema=vol.Schema(_DEVICE_SCHEMA),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT,
        handle_import,
        schema=vol.Schema({**_DEVICE_SCHEMA, vol.Required("payload"): cv.string}),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EzoConfigEntry) -> bool:
    """Set up one EZO Complete-ORP from a config entry."""
    coordinator = EzoCoordinator(hass, entry)
    try:
        await coordinator.async_setup()
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, Exception):
        await coordinator.async_shutdown()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator._async_sync_device_name()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info(
        "EZO Complete-ORP ready: port=%s serial=%s fw=%s",
        coordinator.client.port,
        coordinator.data.serial_number,
        coordinator.data.firmware,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EzoConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options or data change."""
    await hass.config_entries.async_reload(entry.entry_id)
