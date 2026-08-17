"""Switch platform for EZO Complete-ORP."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EzoCoordinator
from .entity import EzoEntity
from .models import EzoDeviceState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzoSwitchEntityDescription(SwitchEntityDescription):
    """Switch bound to coordinator helpers."""

    is_on_fn: Callable[[EzoDeviceState], bool | None]
    turn_on_fn: Callable[[EzoCoordinator], Awaitable[None]]
    turn_off_fn: Callable[[EzoCoordinator], Awaitable[None]]


SWITCHES: tuple[EzoSwitchEntityDescription, ...] = (
    EzoSwitchEntityDescription(
        key="continuous",
        translation_key="continuous",
        is_on_fn=lambda s: s.continuous,
        turn_on_fn=lambda c: c.async_set_continuous(True),
        turn_off_fn=lambda c: c.async_set_continuous(False),
    ),
    EzoSwitchEntityDescription(
        key="led",
        translation_key="led",
        is_on_fn=lambda s: s.led,
        turn_on_fn=lambda c: c.async_set_led(True),
        turn_off_fn=lambda c: c.async_set_led(False),
    ),
    EzoSwitchEntityDescription(
        key="orp_extended",
        translation_key="orp_extended",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        is_on_fn=lambda s: s.orp_extended,
        turn_on_fn=lambda c: c.async_set_orp_extended(True),
        turn_off_fn=lambda c: c.async_set_orp_extended(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[EzoCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZO switches."""
    coordinator = entry.runtime_data
    async_add_entities(EzoSwitch(coordinator, description) for description in SWITCHES)


class EzoSwitch(EzoEntity, SwitchEntity):
    """On/off control for an EZO register."""

    entity_description: EzoSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return switch state from the snapshot."""
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the feature on."""
        await self.entity_description.turn_on_fn(self.coordinator)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the feature off."""
        await self.entity_description.turn_off_fn(self.coordinator)
