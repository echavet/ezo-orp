"""Sensor platform for EZO Complete-ORP."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfElectricPotential
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import EzoCoordinator
from .entity import EzoEntity
from .models import EzoDeviceState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoSensorEntityDescription(SensorEntityDescription):
    """Sensor description bound to a snapshot field."""

    value_fn: Callable[[EzoDeviceState], StateType]
    extra_fn: Callable[[EzoDeviceState], dict[str, Any]] | None = None


def _calibrated_state(state: EzoDeviceState) -> str | None:
    if state.calibrated is None:
        return None
    return "calibrated" if state.calibrated else "not_calibrated"


SENSORS: tuple[EzoSensorEntityDescription, ...] = (
    EzoSensorEntityDescription(
        key="orp",
        translation_key="orp",
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.orp,
        extra_fn=lambda s: {
            "calibrated": s.calibrated,
            "extended_scale": s.orp_extended,
            "continuous": s.continuous,
            "last_raw": s.last_raw,
        },
    ),
    EzoSensorEntityDescription(
        key="device_info",
        translation_key="device_info",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (
            f"{s.device_type},{s.firmware}" if s.device_type and s.firmware else s.device_type
        ),
        extra_fn=lambda s: {"device_type": s.device_type, "firmware": s.firmware},
    ),
    EzoSensorEntityDescription(
        key="status_reason",
        translation_key="status_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["power", "software", "brownout", "watchdog", "unknown"],
        value_fn=lambda s: s.status_reason,
        extra_fn=lambda s: {"code": s.status_reason_code},
    ),
    EzoSensorEntityDescription(
        key="status_voltage",
        translation_key="status_voltage",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.status_voltage,
    ),
    EzoSensorEntityDescription(
        key="calibration_state",
        translation_key="calibration_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=["calibrated", "not_calibrated"],
        value_fn=_calibrated_state,
        extra_fn=lambda s: {
            "orp": s.orp,
            "last_raw": s.last_raw,
        },
    ),
    EzoSensorEntityDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.firmware,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzoCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZO sensors."""
    coordinator = entry.runtime_data
    async_add_entities(EzoSensor(coordinator, description) for description in SENSORS)


class EzoSensor(EzoEntity, SensorEntity):
    """Coordinator-backed sensor."""

    entity_description: EzoSensorEntityDescription

    @property
    def native_value(self) -> StateType:
        """Return the snapshot value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Optional extra attributes."""
        extra_fn = self.entity_description.extra_fn
        if extra_fn is None:
            return None
        return extra_fn(self.coordinator.data)
