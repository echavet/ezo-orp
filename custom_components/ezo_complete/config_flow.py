"""Config Flow, Options Flow, USB discovery and reconfigure."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import usb
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    SOURCE_RECONFIGURE,
    SOURCE_USB,
)
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .client import EzoClientError, EzoNotOrpError, probe_ezo_orp
from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_CONTINUOUS_INTERVAL,
    CONF_CONTINUOUS_ON_START,
    CONF_DEVICE_TYPE,
    CONF_FIRMWARE,
    CONF_SERIAL_NUMBER,
    CONF_UPDATE_INTERVAL,
    CONTINUOUS_INTERVAL_MAX,
    CONTINUOUS_INTERVAL_MIN,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTINUOUS_INTERVAL,
    DEFAULT_CONTINUOUS_ON_START,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SUPPORTED_DEVICE_TYPE,
)
from .protocol import unique_id_from_serial

_LOGGER = logging.getLogger(__name__)


class EzoCompleteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup from USB discovery or a manual serial-port pick."""

    VERSION = 1

    def __init__(self) -> None:
        self._port: str | None = None
        self._serial_number: str | None = None
        self._firmware: str | None = None
        self._device_type: str = SUPPORTED_DEVICE_TYPE
        self._discovery_name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual setup: serial port selector + optional baudrate."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT].strip()
            baudrate = int(user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
            name = (user_input.get(CONF_NAME) or DEFAULT_NAME).strip() or DEFAULT_NAME
            error = await self._async_validate_and_set_unique_id(port, baudrate)
            if error:
                errors["base"] = error
            else:
                return self._async_build_entry(port, baudrate, name)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_PORT): SerialPortSelector(),
                        vol.Optional(
                            CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)
                        ): SelectSelector(
                            SelectSelectorConfig(
                                options=[str(rate) for rate in BAUDRATES],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Optional(CONF_NAME, default=DEFAULT_NAME): TextSelector(),
                    }
                ),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """USB matcher hit: resolve a stable path, probe ``i``, require ORP."""
        device = await self.hass.async_add_executor_job(
            usb.get_serial_by_id, discovery_info.device
        )
        self._port = device
        self._serial_number = discovery_info.serial_number
        self._discovery_name = discovery_info.description or DEFAULT_NAME

        error = await self._async_validate_and_set_unique_id(
            device, DEFAULT_BAUDRATE, serial_number=discovery_info.serial_number
        )
        if error == "not_orp":
            return self.async_abort(reason="not_orp")
        if error == "cannot_connect":
            return self.async_abort(reason="cannot_connect")
        if error:
            return self.async_abort(reason=error)

        self._abort_if_unique_id_configured(
            updates={CONF_PORT: device, CONF_SERIAL_NUMBER: self._serial_number}
        )
        self.context["title_placeholders"] = {
            CONF_NAME: self._discovery_name or DEFAULT_NAME
        }
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a friendly name after a successful USB probe."""
        if user_input is not None:
            assert self._port is not None
            name = (user_input.get(CONF_NAME) or DEFAULT_NAME).strip() or DEFAULT_NAME
            return self._async_build_entry(self._port, DEFAULT_BAUDRATE, name)

        return self.async_show_form(
            step_id="usb_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=self._discovery_name or DEFAULT_NAME
                    ): TextSelector(),
                }
            ),
            description_placeholders={
                "port": self._port or "",
                "serial": self._serial_number or "",
                "firmware": self._firmware or "",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the serial path or baudrate of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_PORT].strip()
            baudrate = int(user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
            name = (user_input.get(CONF_NAME) or entry.title).strip() or entry.title
            error = await self._async_validate_and_set_unique_id(
                port,
                baudrate,
                serial_number=entry.data.get(CONF_SERIAL_NUMBER),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=name,
                    data={
                        **entry.data,
                        CONF_PORT: port,
                        CONF_BAUDRATE: baudrate,
                        CONF_NAME: name,
                        CONF_SERIAL_NUMBER: self._serial_number
                        or entry.data.get(CONF_SERIAL_NUMBER),
                        CONF_FIRMWARE: self._firmware or entry.data.get(CONF_FIRMWARE),
                        CONF_DEVICE_TYPE: self._device_type,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_PORT): SerialPortSelector(),
                        vol.Optional(CONF_BAUDRATE): SelectSelector(
                            SelectSelectorConfig(
                                options=[str(rate) for rate in BAUDRATES],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Optional(CONF_NAME): TextSelector(),
                    }
                ),
                {
                    CONF_PORT: entry.data.get(CONF_PORT),
                    CONF_BAUDRATE: str(entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
                    CONF_NAME: entry.data.get(CONF_NAME, entry.title),
                },
            ),
            errors=errors,
        )

    async def _async_validate_and_set_unique_id(
        self,
        port: str,
        baudrate: int,
        serial_number: str | None = None,
    ) -> str | None:
        """Probe ``i``, require ORP, set the unique ID. Return an error key."""
        try:
            info = await probe_ezo_orp(port, baudrate=baudrate)
        except EzoNotOrpError:
            return "not_orp"
        except (EzoClientError, OSError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Cannot probe %s: %s", port, err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error probing %s", port)
            return "unknown"

        self._firmware = info.firmware
        self._device_type = info.device_type or SUPPORTED_DEVICE_TYPE
        if serial_number:
            self._serial_number = serial_number
        elif not self._serial_number:
            self._serial_number = await self._async_serial_from_port(port)

        unique_id = unique_id_from_serial(self._serial_number, self._device_type)
        await self.async_set_unique_id(unique_id)
        if self.source not in (SOURCE_RECONFIGURE, SOURCE_USB):
            self._abort_if_unique_id_configured()
        elif self.source == SOURCE_RECONFIGURE:
            abort_mismatch = getattr(self, "_abort_if_unique_id_mismatch", None)
            if abort_mismatch is not None:
                abort_mismatch()
        return None

    async def _async_serial_from_port(self, port: str) -> str | None:
        """Best-effort FTDI serial lookup via serialx port listing."""
        try:
            import serialx
        except ImportError:
            return None

        try:
            ports = await serialx.async_list_serial_ports()
        except (OSError, TimeoutError):
            return None
        for info in ports:
            if info.device == port or info.resolved_device == port:
                return info.serial_number
        return None

    def _async_build_entry(
        self, port: str, baudrate: int, name: str
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name,
            data={
                CONF_PORT: port,
                CONF_BAUDRATE: baudrate,
                CONF_NAME: name,
                CONF_SERIAL_NUMBER: self._serial_number,
                CONF_DEVICE_TYPE: self._device_type,
                CONF_FIRMWARE: self._firmware,
            },
            options={
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_CONTINUOUS_ON_START: DEFAULT_CONTINUOUS_ON_START,
                CONF_CONTINUOUS_INTERVAL: DEFAULT_CONTINUOUS_INTERVAL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options handler."""
        return EzoCompleteOptionsFlow()


class EzoCompleteOptionsFlow(OptionsFlow):
    """Update interval, continuous-on-start, continuous period."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
                    CONF_CONTINUOUS_ON_START: bool(
                        user_input[CONF_CONTINUOUS_ON_START]
                    ),
                    CONF_CONTINUOUS_INTERVAL: int(
                        user_input[CONF_CONTINUOUS_INTERVAL]
                    ),
                },
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=300, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_CONTINUOUS_ON_START,
                        default=options.get(
                            CONF_CONTINUOUS_ON_START, DEFAULT_CONTINUOUS_ON_START
                        ),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_CONTINUOUS_INTERVAL,
                        default=options.get(
                            CONF_CONTINUOUS_INTERVAL, DEFAULT_CONTINUOUS_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=CONTINUOUS_INTERVAL_MIN,
                            max=CONTINUOUS_INTERVAL_MAX,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
