"""Text platform for the EZO device name."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextEntityDescription, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EzoCoordinator
from .entity import EzoEntity

PARALLEL_UPDATES = 0

NAME_DESCRIPTION = TextEntityDescription(
    key="device_name",
    translation_key="device_name",
    entity_category=EntityCategory.CONFIG,
    entity_registry_enabled_default=False,
    native_min=0,
    native_max=16,
    mode=TextMode.TEXT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzoCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the optional device-name entity."""
    async_add_entities([EzoNameText(entry.runtime_data, NAME_DESCRIPTION)])


class EzoNameText(EzoEntity, TextEntity):
    """Read/write EZO ``Name`` register."""

    @property
    def native_value(self) -> str | None:
        """Return the name stored on the circuit."""
        return self.coordinator.data.device_name

    async def async_set_value(self, value: str) -> None:
        """Write a new name (max 16 characters)."""
        await self.coordinator.async_set_device_name(value)
