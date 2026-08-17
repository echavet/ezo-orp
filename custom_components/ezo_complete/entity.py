"""Base entity for EZO Complete-ORP."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER, MODEL
from .coordinator import EzoCoordinator


class EzoEntity(CoordinatorEntity[EzoCoordinator]):
    """Shared device info and unique IDs."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: EzoCoordinator,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.unique_id}_{description.key}"
        serial = coordinator.entry.data.get("serial_number")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.unique_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=coordinator.device_name,
            sw_version=coordinator.data.firmware,
            serial_number=serial,
            configuration_url="https://atlas-scientific.com/orp/ezo-complete-orp/",
        )
