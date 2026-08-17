"""Button platform for EZO Complete-ORP."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_CALIBRATION_VALUE
from .coordinator import EzoCoordinator
from .entity import EzoEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoButtonEntityDescription(ButtonEntityDescription):
    """Button that invokes a coordinator coroutine."""

    press_fn: Callable[[EzoCoordinator], Awaitable[None]]


async def _calibrate_225(coordinator: EzoCoordinator) -> None:
    await coordinator.async_calibrate(DEFAULT_CALIBRATION_VALUE)


async def _calibrate_custom(coordinator: EzoCoordinator) -> None:
    await coordinator.async_calibrate(coordinator.pending_calibration_value)


BUTTONS: tuple[EzoButtonEntityDescription, ...] = (
    EzoButtonEntityDescription(
        key="calibrate_225",
        translation_key="calibrate_225",
        press_fn=_calibrate_225,
    ),
    EzoButtonEntityDescription(
        key="calibrate_custom",
        translation_key="calibrate_custom",
        press_fn=_calibrate_custom,
    ),
    EzoButtonEntityDescription(
        key="calibrate_clear",
        translation_key="calibrate_clear",
        press_fn=lambda c: c.async_calibrate_clear(),
    ),
    EzoButtonEntityDescription(
        key="find",
        translation_key="find",
        press_fn=lambda c: c.async_find(),
    ),
    EzoButtonEntityDescription(
        key="sleep",
        translation_key="sleep",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_sleep(),
    ),
    EzoButtonEntityDescription(
        key="export_calibration",
        translation_key="export_calibration",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.async_export_calibration(),
    ),
    EzoButtonEntityDescription(
        key="factory_reset",
        translation_key="factory_reset",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        press_fn=lambda c: c.async_factory_reset(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzoCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZO buttons."""
    coordinator = entry.runtime_data
    async_add_entities(EzoButton(coordinator, description) for description in BUTTONS)


class EzoButton(EzoEntity, ButtonEntity):
    """One-shot EZO command."""

    entity_description: EzoButtonEntityDescription

    async def async_press(self) -> None:
        """Run the bound command."""
        await self.entity_description.press_fn(self.coordinator)
