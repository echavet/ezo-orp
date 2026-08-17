"""Diagnostics dump for EZO Complete-ORP."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import EzoCoordinator

TO_REDACT = {"serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[EzoCoordinator]
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "connected": coordinator.client.connected,
        "last_update_success": coordinator.last_update_success,
        "device": {
            "port": state.port,
            "baudrate": state.baudrate,
            "device_type": state.device_type,
            "firmware": state.firmware,
            "device_name": state.device_name,
            "orp": state.orp,
            "continuous": state.continuous,
            "continuous_interval": state.continuous_interval,
            "calibrated": state.calibrated,
            "led": state.led,
            "orp_extended": state.orp_extended,
            "status_reason": state.status_reason,
            "status_voltage": state.status_voltage,
            "sleeping": state.sleeping,
            "export_data": state.export_data,
        },
        "last_raw_lines": list(state.last_lines),
    }
