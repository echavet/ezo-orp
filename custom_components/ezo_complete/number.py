"""Number platform for EZO Complete-ORP."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONTINUOUS_INTERVAL_MAX,
    CONTINUOUS_INTERVAL_MIN,
    DEFAULT_CALIBRATION_VALUE,
    ORP_RANGE_EXTENDED,
)
from .coordinator import EzoCoordinator
from .entity import EzoEntity

PARALLEL_UPDATES = 0

CAL_NUMBER = NumberEntityDescription(
    key="calibration_value",
    translation_key="calibration_value",
    native_min_value=ORP_RANGE_EXTENDED[0],
    native_max_value=ORP_RANGE_EXTENDED[1],
    native_step=1,
    native_unit_of_measurement="mV",
    mode=NumberMode.BOX,
)

INTERVAL_NUMBER = NumberEntityDescription(
    key="continuous_interval",
    translation_key="continuous_interval",
    entity_category=EntityCategory.CONFIG,
    native_min_value=CONTINUOUS_INTERVAL_MIN,
    native_max_value=CONTINUOUS_INTERVAL_MAX,
    native_step=1,
    native_unit_of_measurement="s",
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzoCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZO numbers."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            EzoCalibrationNumber(coordinator, CAL_NUMBER),
            EzoContinuousIntervalNumber(coordinator, INTERVAL_NUMBER),
        ]
    )


class EzoCalibrationNumber(EzoEntity, RestoreEntity, NumberEntity):
    """Local calibration setpoint used by the custom-calibrate button.

    The value is never sent to the circuit until the user presses
    *Calibrate custom*. That keeps calibration from happening blindly.
    """

    def __init__(
        self,
        coordinator: EzoCoordinator,
        description: NumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self._attr_native_value = DEFAULT_CALIBRATION_VALUE

    async def async_added_to_hass(self) -> None:
        """Restore the last setpoint."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._attr_native_value = float(last.state)
            except (TypeError, ValueError):
                self._attr_native_value = DEFAULT_CALIBRATION_VALUE
        assert self._attr_native_value is not None
        self.coordinator.pending_calibration_value = float(self._attr_native_value)

    async def async_set_native_value(self, value: float) -> None:
        """Store the setpoint locally."""
        self._attr_native_value = value
        self.coordinator.pending_calibration_value = value
        self.async_write_ha_state()


class EzoContinuousIntervalNumber(EzoEntity, NumberEntity):
    """Continuous-mode period written with ``C,<n>``."""

    @property
    def native_value(self) -> float | None:
        """Return the last queried interval."""
        interval = self.coordinator.data.continuous_interval
        if interval is None:
            return None
        return float(interval)

    async def async_set_native_value(self, value: float) -> None:
        """Write the interval to the circuit."""
        await self.coordinator.async_set_continuous_interval(int(value))
