"""Async Atlas EZO UART client built on serialx."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import logging

from .const import (
    COMMAND_TIMEOUT,
    OPEN_SETTLE,
    READ_COMMAND_TIMEOUT,
    WAKE_SETTLE,
)
from .protocol import (
    CR,
    DeviceInfoResponse,
    EzoResponse,
    LineKind,
    ParsedLine,
    encode_command,
    parse_device_info,
    parse_line,
)

_LOGGER = logging.getLogger(__name__)

# Commands that put the circuit to sleep: no *OK is expected.
_NO_REPLY_COMMANDS = {"sleep"}
# Commands that reboot the circuit.
_REBOOT_COMMANDS = {"factory"}


class EzoClientError(Exception):
    """Raised when an EZO command fails or the device is unreachable."""


class EzoNotOrpError(EzoClientError):
    """Raised when the serial device is not an EZO ORP circuit."""


class EzoSerialClient:
    """Talk to one EZO Complete module over UART.

    All I/O is serialized by ``_lock``. A coordinator listen loop and
    explicit commands share the same lock so they never interleave bytes.
    """

    def __init__(self, port: str, baudrate: int = 9600) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial: object | None = None
        self._lock = asyncio.Lock()
        self._connected = False

    @property
    def connected(self) -> bool:
        """Return True if the serial port is believed open."""
        return self._connected and self._serial is not None

    async def connect(self) -> None:
        """Open the serial port and wait for the circuit to settle."""
        import serialx

        if self.connected:
            return
        serial = serialx.async_serial_for_url(
            self.port,
            baudrate=self.baudrate,
            exclusive=True,
        )
        await serial.open()
        self._serial = serial
        self._connected = True
        await asyncio.sleep(OPEN_SETTLE)
        await self._drain_unlocked(0.25)
        _LOGGER.debug("Opened EZO serial port %s @ %s", self.port, self.baudrate)

    async def disconnect(self) -> None:
        """Close the serial port."""
        serial = self._serial
        self._serial = None
        self._connected = False
        if serial is None:
            return
        close = getattr(serial, "close", None)
        if close is None:
            return
        try:
            await close()
        except (OSError, TimeoutError) as err:
            _LOGGER.debug("Error closing %s: %s", self.port, err)

    async def command(self, cmd: str, timeout: float | None = None) -> EzoResponse:
        """Send a command and collect the response lines."""
        async with self._lock:
            return await self._command_unlocked(cmd, timeout)

    async def listen(self, timeout: float) -> list[ParsedLine]:
        """Read unsolicited lines (continuous mode) for up to ``timeout`` seconds."""
        async with self._lock:
            return await self._read_lines_unlocked(timeout)

    async def wake(self) -> None:
        """Wake a sleeping circuit by sending CR and waiting."""
        async with self._lock:
            await self._write_unlocked(b"\r")
            await asyncio.sleep(WAKE_SETTLE)
            await self._drain_unlocked(0.3)

    async def identify(
        self, timeout: float = COMMAND_TIMEOUT, retries: int = 3
    ) -> DeviceInfoResponse:
        """Send ``i`` and require an ORP identity.

        After Factory (or with continuous mode still on) the UART is full of
        numeric readings. Stop the stream, drain, then retry ``i``.
        """
        await self.wake()
        last_raw = "<empty>"
        for attempt in range(max(retries, 1)):
            try:
                await self.command("C,0", timeout=timeout)
            except EzoClientError:
                pass
            async with self._lock:
                await self._drain_unlocked(0.6)
            response = await self.command("i", timeout=timeout)
            last_raw = " | ".join(response.raw_lines) or "<empty>"
            info = parse_device_info(response)
            if info is not None and info.is_orp:
                return info
            _LOGGER.info(
                "identify attempt %s/%s got %s",
                attempt + 1,
                retries,
                last_raw,
            )
            await asyncio.sleep(0.4)
        raise EzoNotOrpError(f"Not an EZO ORP device: {last_raw}")

    async def _command_unlocked(
        self, cmd: str, timeout: float | None = None
    ) -> EzoResponse:
        if not self.connected:
            raise EzoClientError("Serial port is not open")
        name = cmd.strip()
        lowered = name.split(",", 1)[0].lower()
        if timeout is None:
            timeout = READ_COMMAND_TIMEOUT if lowered == "r" else COMMAND_TIMEOUT

        drain_s = 0.5 if lowered in {"c", "i", "factory"} else 0.05
        await self._drain_unlocked(drain_s)
        await self._write_unlocked(encode_command(name))

        if lowered in _NO_REPLY_COMMANDS:
            return EzoResponse(command=name)

        lines = await self._read_lines_unlocked(timeout, command=name)
        if lowered in _REBOOT_COMMANDS:
            await asyncio.sleep(OPEN_SETTLE)
            extra = await self._read_lines_unlocked(1.0, command=name)
            lines.extend(extra)
        return EzoResponse(command=name, lines=lines)

    async def _write_unlocked(self, data: bytes) -> None:
        serial = self._require_serial()
        try:
            await serial.write(data)
            flush = getattr(serial, "flush", None)
            if flush is not None:
                await flush()
        except (OSError, TimeoutError) as err:
            self._connected = False
            raise EzoClientError(f"Write failed on {self.port}: {err}") from err

    async def _read_lines_unlocked(
        self, timeout: float, command: str | None = None
    ) -> list[ParsedLine]:
        """Read CR-terminated lines until ``timeout`` elapses."""
        serial = self._require_serial()
        lines: list[ParsedLine] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.05)
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(
                    serial.readuntil(CR),
                    timeout=remaining,
                )
            except TimeoutError:
                break
            except (OSError, serialx_os_error()) as err:
                self._connected = False
                raise EzoClientError(f"Read failed on {self.port}: {err}") from err
            text = _decode_line(raw)
            if not text:
                continue
            parsed = parse_line(text)
            lines.append(parsed)
            _LOGGER.debug("EZO %s << %s", self.port, text)
            if _is_terminal(lines, command):
                # Give a tiny extra window for a trailing *OK after a payload.
                if parsed.kind is not LineKind.STATUS:
                    extra = await self._read_one_unlocked(0.15)
                    if extra is not None:
                        lines.append(extra)
                break
        return lines

    async def _read_one_unlocked(self, timeout: float) -> ParsedLine | None:
        serial = self._require_serial()
        try:
            raw = await asyncio.wait_for(serial.readuntil(CR), timeout=timeout)
        except (TimeoutError, OSError):
            return None
        text = _decode_line(raw)
        return parse_line(text) if text else None

    async def _drain_unlocked(self, timeout: float) -> None:
        """Discard whatever is sitting in the UART buffer."""
        try:
            await self._read_lines_unlocked(timeout)
        except EzoClientError:
            return

    def _require_serial(self):
        serial = self._serial
        if serial is None:
            self._connected = False
            raise EzoClientError("Serial port is not open")
        return serial


def serialx_os_error() -> tuple[type[BaseException], ...]:
    """Return extra serialx exceptions if the library is importable."""
    try:
        import serialx
    except ImportError:
        return ()
    extra: list[type[BaseException]] = []
    for name in ("SerialException", "UnknownUriScheme"):
        exc = getattr(serialx, name, None)
        if isinstance(exc, type) and issubclass(exc, BaseException):
            extra.append(exc)
    return tuple(extra)


def _decode_line(raw: bytes) -> str:
    return raw.decode("ascii", errors="ignore").strip("\r\n\x00 ").strip()


def _is_terminal(lines: Iterable[ParsedLine], command: str | None = None) -> bool:
    """True once we have a complete reply for ``command``.

    A leftover continuous reading must not complete ``Cal``, ``i``, etc.
    When ``command`` is omitted (listen / drain), keep reading until timeout.
    """
    if not command:
        return False
    verb = command.split(",", 1)[0].lower()
    for line in lines:
        if line.kind is LineKind.STATUS and line.status_code in {"OK", "ER", "OV", "UV"}:
            return True
        if verb == "r" and line.kind is LineKind.READING:
            return True
        if verb != "r" and line.kind is LineKind.QUERY:
            return True
    return False


async def probe_ezo_orp(
    port: str,
    baudrate: int = 9600,
    timeout: float = COMMAND_TIMEOUT,
) -> DeviceInfoResponse:
    """Open ``port``, send ``i``, require ORP, then close.

    Used by the Config Flow so we never create an entry for a generic FTDI
    gadget.
    """
    client = EzoSerialClient(port, baudrate=baudrate)
    try:
        await client.connect()
        return await client.identify(timeout=timeout)
    finally:
        await client.disconnect()
