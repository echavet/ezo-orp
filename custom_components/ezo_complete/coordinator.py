"""DataUpdateCoordinator for EZO Complete-ORP."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import timedelta
import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EzoClientError, EzoNotOrpError, EzoSerialClient
from .const import (
    CONF_BAUDRATE,
    CONF_CONTINUOUS_INTERVAL,
    CONF_CONTINUOUS_ON_START,
    CONF_SERIAL_NUMBER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BAUDRATE,
    DEFAULT_CALIBRATION_VALUE,
    DEFAULT_CONTINUOUS_INTERVAL,
    DEFAULT_CONTINUOUS_ON_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FACTORY_ARM_SECONDS,
    RESPONSE_CODE_ENABLE_COMMANDS,
    RAW_LINE_HISTORY,
    RECONNECT_DELAY,
)
from .models import EzoDeviceState
from .protocol import (
    LineKind,
    ParsedLine,
    is_usb_product_name,
    parse_calibrated,
    parse_continuous,
    parse_device_info,
    parse_export_count,
    parse_flag,
    parse_led,
    parse_name,
    parse_status,
    resolve_display_name,
)

_LOGGER = logging.getLogger(__name__)


class EzoCoordinator(DataUpdateCoordinator[EzoDeviceState]):
    """Owns the serial client, listen loop, and device snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        options = entry.options
        interval = int(options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=entry.data.get(CONF_NAME) or entry.title or DOMAIN,
            update_interval=timedelta(seconds=max(interval, 1)),
        )
        self.entry = entry
        self.client = EzoSerialClient(
            port=entry.data[CONF_PORT],
            baudrate=int(entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
        )
        self.data = EzoDeviceState(
            port=self.client.port,
            baudrate=self.client.baudrate,
            serial_number=entry.data.get(CONF_SERIAL_NUMBER),
        )
        self._listen_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._unavailable_logged = False
        self._factory_armed_until: float = 0.0
        self._raw_history: deque[str] = deque(maxlen=RAW_LINE_HISTORY)
        self._pause_listen = False
        self._last_diag_at = 0.0
        self.pending_calibration_value = DEFAULT_CALIBRATION_VALUE

    @property
    def unique_id(self) -> str:
        """Config-entry unique ID (FTDI serial + type)."""
        return self.entry.unique_id or self.entry.entry_id

    @property
    def device_name(self) -> str:
        """Friendly name: EZO Name register, never the FTDI product string."""
        return resolve_display_name(
            ezo_name=self.data.device_name,
            configured=self.entry.data.get(CONF_NAME) or self.entry.title,
        )

    @property
    def continuous_on_start(self) -> bool:
        """Whether continuous mode should be enabled after connect."""
        return bool(
            self.entry.options.get(CONF_CONTINUOUS_ON_START, DEFAULT_CONTINUOUS_ON_START)
        )

    @property
    def configured_continuous_interval(self) -> int:
        """Seconds between continuous readings."""
        return int(
            self.entry.options.get(
                CONF_CONTINUOUS_INTERVAL, DEFAULT_CONTINUOUS_INTERVAL
            )
        )

    async def async_setup(self) -> None:
        """Open the port, identify the circuit, start the listen loop."""
        try:
            await self.client.connect()
            await self._initialize_device()
        except (EzoClientError, OSError, TimeoutError) as err:
            await self.client.disconnect()
            raise ConfigEntryNotReady(f"Cannot open {self.client.port}: {err}") from err
        self._listen_task = self.entry.async_create_background_task(
            self.hass, self._listen_loop(), name=f"{DOMAIN}_listen"
        )
        self._mark_available()

    async def async_shutdown(self) -> None:
        """Stop background work and close the serial port."""
        for task in (self._listen_task, self._reconnect_task):
            if task is not None:
                task.cancel()
        self._listen_task = None
        self._reconnect_task = None
        await self.client.disconnect()

    async def _async_update_data(self) -> EzoDeviceState:
        """Poll a single reading when continuous mode is off; refresh diagnostics."""
        if not self.client.connected:
            raise UpdateFailed("EZO Complete-ORP is disconnected")
        try:
            if not self.data.continuous:
                await self._command("R")
            elif time.monotonic() - self._last_diag_at >= 60:
                await self._refresh_diagnostics()
        except EzoClientError as err:
            self._schedule_reconnect()
            raise UpdateFailed(str(err)) from err
        return self.data

    async def async_set_continuous(self, enabled: bool) -> None:
        """Enable or disable continuous readings."""
        if enabled:
            interval = self.data.continuous_interval or self.configured_continuous_interval
            await self._command(f"C,{interval}")
        else:
            await self._command("C,0")
        await self._command("C,?")

    async def async_set_continuous_interval(self, seconds: int) -> None:
        """Set the continuous-mode period (and enable it)."""
        await self._command(f"C,{int(seconds)}")
        await self._command("C,?")

    async def async_set_led(self, enabled: bool) -> None:
        """Turn the onboard LED on or off."""
        await self._command("L,1" if enabled else "L,0")
        await self._command("L,?")

    async def async_calibrate(self, value: float) -> None:
        """Single-point calibration at ``value`` mV (live sensor stays visible)."""
        number = int(round(value))
        await self._async_run_calibration(f"Cal,{number}", expect_calibrated=True, mv=number)

    async def async_calibrate_clear(self) -> None:
        """Erase stored calibration."""
        await self._async_run_calibration("Cal,clear", expect_calibrated=False, mv=None)

    async def _async_run_calibration(
        self,
        cal_command: str,
        *,
        expect_calibrated: bool,
        mv: int | None,
    ) -> None:
        """Stop the UART stream, send Cal, refresh Cal,? + R, restore continuous."""
        resume_continuous = self.data.continuous is not False
        interval = self.data.continuous_interval or self.configured_continuous_interval
        error_text: str | None = None
        try:
            await self._command("C,0", ignore_error=True)
            await asyncio.sleep(0.2)
            cal = await self._command(cal_command)
            if not cal.ok and cal.error_code:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={
                        "command": cal_command,
                        "error": cal.error_code,
                    },
                )
            query = await self._command("Cal,?")
            calibrated = parse_calibrated(query)
            if calibrated is None:
                calibrated = expect_calibrated
            state = self.data.copy()
            state.calibrated = calibrated
            self.async_set_updated_data(state)
            reading = await self._command("R", ignore_error=True)
            orp = reading.first_reading() if reading is not None else self.data.orp
            if orp is not None:
                state = self.data.copy()
                state.orp = orp
                state.calibrated = calibrated
                self.async_set_updated_data(state)
            _LOGGER.info(
                "Calibration %s done: Cal,?= %s ORP=%s reply=%s",
                cal_command,
                "1" if calibrated else "0",
                orp,
                " | ".join(cal.raw_lines + query.raw_lines),
            )
            self._notify_calibration(
                success=True,
                command=cal_command,
                calibrated=calibrated,
                orp=orp,
                mv=mv,
            )
        except HomeAssistantError as err:
            error_text = str(err)
            _LOGGER.info("Calibration %s failed: %s", cal_command, err)
            self._notify_calibration(
                success=False,
                command=cal_command,
                error=error_text,
                mv=mv,
            )
            raise
        finally:
            if resume_continuous:
                await self._command(f"C,{interval}", ignore_error=True)
                await self._command("C,?", ignore_error=True)

    async def async_sleep(self) -> None:
        """Put the circuit to sleep. Any later command wakes it."""
        await self._command("Sleep")
        state = self.data.copy()
        state.sleeping = True
        self.async_set_updated_data(state)

    async def async_find(self) -> None:
        """Blink the LED white so the physical module can be located."""
        await self._command("Find")

    async def async_set_device_name(self, name: str) -> None:
        """Write the EZO ``Name`` register (max 16 chars)."""
        cleaned = name.strip()[:16]
        if cleaned:
            await self._command(f"Name,{cleaned}")
        else:
            await self._command("Name,")
        await self._command("Name,?")

    async def async_set_orp_extended(self, enabled: bool) -> None:
        """Enable or disable the extended ORP scale."""
        await self._command("ORPext,1" if enabled else "ORPext,0")
        await self._command("ORPext,?")

    async def async_factory_reset(self, *, confirm: bool = False) -> None:
        """Factory reset. Requires a second press within 30 s, or ``confirm``."""
        now = time.monotonic()
        if not confirm and now > self._factory_armed_until:
            self._factory_armed_until = now + FACTORY_ARM_SECONDS
            state = self.data.copy()
            state.factory_armed = True
            self.async_set_updated_data(state)
            _LOGGER.warning(
                "Factory reset armed for %s s — press again to confirm",
                FACTORY_ARM_SECONDS,
            )
            return
        self._factory_armed_until = 0.0
        try:
            await self._command("C,0", ignore_error=True)
            await self._command("Factory", ignore_error=True)
            # Circuit reboots then comes back in factory continuous mode.
            await asyncio.sleep(2.5)
            await self._command("C,0", ignore_error=True)
            await asyncio.sleep(0.3)
            await self._initialize_device()
        except (EzoNotOrpError, EzoClientError) as err:
            _LOGGER.info("Factory reset re-init failed: %s", err)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={
                    "command": "Factory",
                    "error": str(err),
                },
            ) from err
        _LOGGER.info("Factory reset complete; device re-identified")
        persistent_notification.async_create(
            self.hass,
            "Factory reset OK — circuit réidentifié (ORP).",
            title="EZO ORP",
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_factory",
        )

    async def async_export_calibration(self) -> str:
        """Dump the calibration payload via repeated ``Export`` commands."""
        first = await self._command("Export")
        count = parse_export_count(first)
        chunks: list[str] = []
        if first.raw_lines:
            chunks.extend(first.raw_lines)
        remaining = count if count is not None else 12
        for _ in range(max(remaining, 0) + 2):
            response = await self._command("Export")
            if not response.raw_lines:
                break
            chunks.extend(response.raw_lines)
            if response.query("export") and parse_export_count(response) == 0:
                break
        payload = "\n".join(chunks)
        state = self.data.copy()
        state.export_data = payload
        self.async_set_updated_data(state)
        return payload

    async def async_import_calibration(self, payload: str) -> None:
        """Send each non-empty line as ``Import,<line>``."""
        lines = [line.strip() for line in payload.splitlines() if line.strip()]
        if not lines:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="import_empty",
            )
        for line in lines:
            cmd = line if line.lower().startswith("import") else f"Import,{line}"
            await self._command(cmd)
        await self._command("Cal,?")

    async def async_send_raw(self, command: str) -> str:
        """Send a raw EZO command and return the collected reply."""
        response = await self._command(command)
        return "\n".join(response.raw_lines)

    async def _initialize_device(self) -> None:
        """Identify the circuit and snapshot its registers."""
        info = await self.client.identify()
        state = self.data.copy()
        state.device_type = info.device_type
        state.firmware = info.firmware
        state.sleeping = False
        state.factory_armed = False
        self.async_set_updated_data(state)

        # Factory default is often continuous-on: stop the stream so queries
        # are not mixed with unsolicited readings.
        await self._command("C,0", ignore_error=True)
        await self._enable_response_codes()
        if self.continuous_on_start:
            await self._command(
                f"C,{self.configured_continuous_interval}", ignore_error=True
            )
        await self._refresh_diagnostics()
        self._last_diag_at = time.monotonic()
        if not self.data.continuous:
            await self._command("R", ignore_error=True)

    async def _enable_response_codes(self) -> None:
        """Turn on *OK framing. Command name differs across EZO firmware."""
        for cmd in RESPONSE_CODE_ENABLE_COMMANDS:
            response = await self._command(cmd, ignore_error=True)
            if response is not None and response.ok:
                _LOGGER.debug("Response codes enabled with %s", cmd)
                return
        _LOGGER.debug("No response-code command accepted; continuing without *OK")

    async def _refresh_diagnostics(self) -> None:
        """Query registers that do not stream in continuous mode."""
        for cmd in ("C,?", "Cal,?", "L,?", "Status", "Name,?", "ORPext,?", "i"):
            await self._command(cmd, ignore_error=True)

    async def _command(self, cmd: str, *, ignore_error: bool = False):
        """Issue a command, pause the listen loop, apply the reply."""
        if not self.client.connected:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
            )
        self._pause_listen = True
        try:
            if self.data.sleeping and cmd.split(",", 1)[0].lower() != "sleep":
                await self.client.wake()
            verb = cmd.split(",", 1)[0].lower()
            log = _LOGGER.info if verb in {"cal", "c", "factory"} else _LOGGER.debug
            log("EZO >> %s", cmd)
            response = await self.client.command(cmd)
            log(
                "EZO << %s",
                " | ".join(response.raw_lines) if response.raw_lines else "<empty>",
            )
        except EzoClientError as err:
            self._schedule_reconnect()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"command": cmd, "error": str(err)},
            ) from err
        finally:
            self._pause_listen = False

        if cmd.split(",", 1)[0].lower() == "sleep":
            return response
        self._apply_lines(response.lines, last_command=cmd)
        if not response.ok:
            verb = cmd.split(",", 1)[0].lower()
            if ignore_error:
                _LOGGER.debug(
                    "Ignoring failed command %s (%s)",
                    cmd,
                    response.error_code or "unknown",
                )
                return response
            # Cal,<n> with response codes off has no *OK; no *ER still means go on.
            if verb == "cal" and response.error_code is None:
                _LOGGER.info("EZO %s: no *OK (response codes off?); continuing", cmd)
                return response
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={
                    "command": cmd,
                    "error": response.error_code or "unknown",
                },
            )
        return response

    async def _listen_loop(self) -> None:
        """Consume continuous-mode readings until cancelled."""
        while True:
            try:
                if self._pause_listen or not self.client.connected:
                    await asyncio.sleep(0.2)
                    continue
                if self.data.continuous is False:
                    await asyncio.sleep(0.5)
                    continue
                # Short reads so a user command can take the lock quickly.
                lines = await self.client.listen(0.4)
                if lines:
                    self._apply_lines(lines)
                    self._mark_available()
            except asyncio.CancelledError:
                raise
            except (EzoClientError, OSError, TimeoutError) as err:
                _LOGGER.debug("Listen loop error: %s", err)
                self._schedule_reconnect()
                await asyncio.sleep(RECONNECT_DELAY)

    def _apply_lines(
        self, lines: list[ParsedLine], last_command: str | None = None
    ) -> None:
        """Merge parsed lines into the published snapshot."""
        if not lines:
            return
        state = self.data.copy()
        for line in lines:
            self._raw_history.append(line.raw)
            if line.kind is LineKind.READING and line.value is not None:
                state.orp = line.value
            elif line.kind is LineKind.QUERY:
                self._apply_query(state, line)
            elif line.status_code == "SL":
                state.sleeping = True
            elif line.status_code == "WA":
                state.sleeping = False
        state.last_raw = lines[-1].raw
        state.last_lines = list(self._raw_history)
        state.factory_armed = time.monotonic() <= self._factory_armed_until
        if last_command and last_command.split(",", 1)[0].lower() != "sleep":
            state.sleeping = False
        if last_command:
            verb = last_command.split(",", 1)[0].lower()
            arg = last_command[len(verb) + 1 :].lower() if "," in last_command else ""
            if verb == "cal" and arg not in {"?", "clear"}:
                if any(line.status_code == "OK" for line in lines) or parse_calibrated(
                    "\n".join(line.raw for line in lines)
                ):
                    state.calibrated = True
            elif verb == "cal" and arg == "clear":
                if any(line.status_code == "OK" for line in lines):
                    state.calibrated = False
        self.async_set_updated_data(state)

    def _apply_query(self, state: EzoDeviceState, line: ParsedLine) -> None:
        key = (line.query_key or "").lower()
        raw = line.raw
        if key == "i":
            info = parse_device_info(raw)
            if info:
                state.device_type = info.device_type
                state.firmware = info.firmware
        elif key == "c":
            cont = parse_continuous(raw)
            if cont:
                state.continuous = cont.enabled
                state.continuous_interval = cont.interval or state.continuous_interval
        elif key == "cal":
            calibrated = parse_calibrated(raw)
            if calibrated is not None:
                state.calibrated = calibrated
        elif key == "l":
            led = parse_led(raw)
            if led is not None:
                state.led = led
        elif key == "status":
            status = parse_status(raw)
            if status:
                state.status_reason = status.reason
                state.status_reason_code = status.reason_code
                state.status_voltage = status.voltage
        elif key == "name":
            name = parse_name(raw)
            if name is not None:
                state.device_name = name
        elif key == "orpext":
            flag = parse_flag(raw, "orpext")
            if flag is not None:
                state.orp_extended = flag
        elif key in {"ok", "o", "response"}:
            flag = parse_flag(raw, key)
            if flag is not None:
                state.response_codes = flag

    def _schedule_reconnect(self) -> None:
        """Start a reconnect task if one is not already running."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._mark_unavailable()
        self._reconnect_task = self.entry.async_create_background_task(
            self.hass, self._reconnect_loop(), name=f"{DOMAIN}_reconnect"
        )

    async def _reconnect_loop(self) -> None:
        """Close and reopen the serial port until the device answers."""
        while True:
            try:
                await self.client.disconnect()
                await asyncio.sleep(RECONNECT_DELAY)
                await self.client.connect()
                await self._initialize_device()
            except asyncio.CancelledError:
                raise
            except (EzoClientError, EzoNotOrpError, OSError, TimeoutError) as err:
                _LOGGER.debug("Reconnect to %s failed: %s", self.client.port, err)
                continue
            self._mark_available()
            return

    def _mark_unavailable(self) -> None:
        if not self._unavailable_logged:
            _LOGGER.warning(
                "EZO Complete-ORP disconnected (%s) — will retry",
                self.client.port,
            )
            self._unavailable_logged = True
        self.last_update_success = False
        self.async_update_listeners()

    def _mark_available(self) -> None:
        if self._unavailable_logged:
            _LOGGER.info("EZO Complete-ORP reconnected (%s)", self.client.port)
            self._unavailable_logged = False
        self.last_update_success = True
        self.async_update_listeners()

    def _notify_calibration(
        self,
        *,
        success: bool,
        command: str,
        calibrated: bool | None = None,
        orp: float | None = None,
        mv: int | None = None,
        error: str | None = None,
    ) -> None:
        """Persistent notification so the UI is not silent after a button press."""
        title = "EZO ORP"
        if success:
            cal_txt = "Cal,?=1" if calibrated else "Cal,?=0"
            orp_txt = f"{orp:.1f} mV" if orp is not None else "n/a"
            target = f"{mv} mV" if mv is not None else command
            message = f"{command} OK — cible {target}, {cal_txt}, ORP={orp_txt}"
        else:
            message = f"{command} failed: {error or 'timeout / *ER'}"
        persistent_notification.async_create(
            self.hass,
            message,
            title=title,
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_calibrate",
        )

    def _async_sync_device_name(self) -> None:
        """Replace an FTDI product title with EZO ORP or the circuit Name."""
        name = self.device_name
        configured = self.entry.data.get(CONF_NAME) or self.entry.title
        if is_usb_product_name(configured) or is_usb_product_name(self.entry.title):
            self.hass.config_entries.async_update_entry(
                self.entry,
                title=name,
                data={**self.entry.data, CONF_NAME: name},
            )
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.unique_id)})
        if device is not None and device.name_by_user is None and device.name != name:
            registry.async_update_device(device.id, name=name)
