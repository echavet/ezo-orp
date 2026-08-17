"""Pure Atlas EZO UART protocol helpers (no I/O, no Home Assistant).

The EZO Complete family speaks ASCII commands terminated by CR. Responses
are either a numeric reading, a ``?Key,value`` query, or a ``*CODE`` status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re

from .const import STATUS_REASON_MAP, SUPPORTED_DEVICE_TYPE

CR = b"\r"
CMD_TERMINATOR = "\r"

# Bare ORP readings: optional sign, digits, optional decimal.
_READING_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


class LineKind(StrEnum):
    """Classification of a single EZO response line."""

    READING = "reading"
    QUERY = "query"
    STATUS = "status"
    OTHER = "other"


class EzoStatusCode(StrEnum):
    """Known ``*CODE`` responses."""

    OK = "OK"
    ER = "ER"
    OV = "OV"
    UV = "UV"
    RS = "RS"
    RE = "RE"
    SL = "SL"
    WA = "WA"


@dataclass(slots=True)
class ParsedLine:
    """One decoded EZO line."""

    kind: LineKind
    raw: str
    value: float | None = None
    query_key: str | None = None
    query_args: tuple[str, ...] = ()
    status_code: str | None = None


@dataclass(slots=True)
class DeviceInfoResponse:
    """Parsed ``?i,<type>,<fw>``."""

    device_type: str
    firmware: str
    raw: str

    @property
    def is_orp(self) -> bool:
        """Return True if this is an ORP circuit."""
        return (
            self.device_type.upper() == SUPPORTED_DEVICE_TYPE
            or SUPPORTED_DEVICE_TYPE in self.raw.upper()
        )


@dataclass(slots=True)
class StatusResponse:
    """Parsed ``?Status,<reason>,<voltage>``."""

    reason_code: str
    reason: str
    voltage: float | None
    raw: str


@dataclass(slots=True)
class ContinuousResponse:
    """Parsed ``?C,<n>``."""

    enabled: bool
    interval: int
    raw: str


@dataclass(slots=True)
class EzoResponse:
    """Collected response for one issued command."""

    command: str
    lines: list[ParsedLine] = field(default_factory=list)

    @property
    def raw_lines(self) -> list[str]:
        """Raw text of every collected line."""
        return [line.raw for line in self.lines]

    @property
    def ok(self) -> bool:
        """True if the device reported ``*OK`` (or no error status)."""
        codes = [line.status_code for line in self.lines if line.kind is LineKind.STATUS]
        if EzoStatusCode.ER in codes or EzoStatusCode.OV in codes:
            return False
        if EzoStatusCode.OK in codes:
            return True
        # Response codes may be disabled: treat a payload without *ER as success.
        return any(line.kind in (LineKind.READING, LineKind.QUERY) for line in self.lines)

    @property
    def error_code(self) -> str | None:
        """First error status, if any."""
        for line in self.lines:
            if line.status_code in {EzoStatusCode.ER, EzoStatusCode.OV, EzoStatusCode.UV}:
                return line.status_code
        return None

    def first_reading(self) -> float | None:
        """First numeric reading in the response."""
        for line in self.lines:
            if line.kind is LineKind.READING and line.value is not None:
                return line.value
        return None

    def query(self, key: str | None = None) -> ParsedLine | None:
        """Return the first query line, optionally filtered by key."""
        for line in self.lines:
            if line.kind is not LineKind.QUERY:
                continue
            if key is None or (line.query_key or "").lower() == key.lower():
                return line
        return None


def encode_command(command: str) -> bytes:
    """Encode an EZO command as CR-terminated ASCII bytes."""
    return f"{command.strip()}{CMD_TERMINATOR}".encode("ascii")


def parse_line(raw: str) -> ParsedLine:
    """Classify and parse a single stripped EZO line."""
    text = raw.strip().strip("\x00")
    if not text:
        return ParsedLine(kind=LineKind.OTHER, raw=text)

    if text.startswith("*"):
        code = text[1:].split(",", 1)[0].strip().upper()
        return ParsedLine(kind=LineKind.STATUS, raw=text, status_code=code)

    if text.startswith("?"):
        body = text[1:]
        parts = [part.strip() for part in body.split(",")]
        key = parts[0] if parts else ""
        return ParsedLine(
            kind=LineKind.QUERY,
            raw=text,
            query_key=key,
            query_args=tuple(parts[1:]),
        )

    if _READING_RE.match(text):
        return ParsedLine(kind=LineKind.READING, raw=text, value=float(text))

    return ParsedLine(kind=LineKind.OTHER, raw=text)


def parse_device_info(response: EzoResponse | str) -> DeviceInfoResponse | None:
    """Parse ``?i,ORP,1.98`` from a response or raw line."""
    line = _query_line(response, "i")
    if line is None:
        # CDC: accept any response that contains ORP (probe may wrap extra noise).
        raw = _raw_blob(response)
        if SUPPORTED_DEVICE_TYPE not in raw.upper():
            return None
        return DeviceInfoResponse(device_type=SUPPORTED_DEVICE_TYPE, firmware="", raw=raw)

    device_type = line.query_args[0] if line.query_args else ""
    firmware = line.query_args[1] if len(line.query_args) > 1 else ""
    return DeviceInfoResponse(
        device_type=device_type,
        firmware=firmware,
        raw=line.raw,
    )


def is_orp_info_response(raw: str) -> bool:
    """Return True if a raw ``i`` reply identifies an ORP circuit."""
    info = parse_device_info(raw)
    return bool(info and info.is_orp)


def parse_status(response: EzoResponse | str) -> StatusResponse | None:
    """Parse ``?Status,P,5.038``."""
    line = _query_line(response, "status")
    if line is None:
        return None
    reason_code = (line.query_args[0] if line.query_args else "U").upper()
    voltage: float | None = None
    if len(line.query_args) > 1:
        try:
            voltage = float(line.query_args[1])
        except ValueError:
            voltage = None
    return StatusResponse(
        reason_code=reason_code,
        reason=STATUS_REASON_MAP.get(reason_code, "unknown"),
        voltage=voltage,
        raw=line.raw,
    )


def parse_continuous(response: EzoResponse | str) -> ContinuousResponse | None:
    """Parse ``?C,0`` / ``?C,1`` / ``?C,5``."""
    line = _query_line(response, "c")
    if line is None:
        return None
    interval = 0
    if line.query_args:
        try:
            interval = int(float(line.query_args[0]))
        except ValueError:
            interval = 0
    return ContinuousResponse(enabled=interval > 0, interval=max(interval, 0), raw=line.raw)


def parse_calibrated(response: EzoResponse | str) -> bool | None:
    """Parse ``?Cal,0`` / ``?Cal,1`` (any casing, including mixed stream lines)."""
    line = _query_line(response, "cal")
    if line is not None and line.query_args:
        try:
            return int(float(line.query_args[0])) > 0
        except ValueError:
            pass
    raw = _raw_blob(response)
    match = re.search(r"\?Cal\s*,\s*(\d+)", raw, flags=re.IGNORECASE)
    if match is None:
        return None
    try:
        return int(match.group(1)) > 0
    except ValueError:
        return None


def parse_led(response: EzoResponse | str) -> bool | None:
    """Parse ``?L,0`` / ``?L,1``."""
    line = _query_line(response, "l")
    if line is None:
        return None
    if not line.query_args:
        return None
    return line.query_args[0] not in {"0", "0.0"}


def parse_name(response: EzoResponse | str) -> str | None:
    """Parse ``?Name,tank`` (empty string if unset)."""
    line = _query_line(response, "name")
    if line is None:
        return None
    return ",".join(line.query_args)


def parse_flag(response: EzoResponse | str, key: str) -> bool | None:
    """Parse a boolean query such as ``?ORPext,1`` or ``?OK,0``."""
    line = _query_line(response, key)
    if line is None or not line.query_args:
        return None
    return line.query_args[0] not in {"0", "0.0"}


def parse_export_count(response: EzoResponse | str) -> int | None:
    """Parse ``?EXPORT,<n>`` (number of calibration dump lines)."""
    line = _query_line(response, "export")
    if line is None or not line.query_args:
        return None
    try:
        return int(float(line.query_args[0]))
    except ValueError:
        return None


_USB_PRODUCT_MARKERS = (
    "FT230X",
    "FT232",
    "FT2232",
    "FT4232",
    "BASIC UART",
    "USB SERIAL",
    "USB-SERIAL",
)


def is_usb_product_name(name: str | None) -> bool:
    """True if ``name`` looks like an FTDI USB product string, not an EZO name."""
    if not name or not name.strip():
        return True
    upper = name.upper()
    return any(marker in upper for marker in _USB_PRODUCT_MARKERS)


def resolve_display_name(
    *,
    ezo_name: str | None = None,
    configured: str | None = None,
    fallback: str = "EZO ORP",
) -> str:
    """Prefer the EZO ``Name`` register, never the FTDI product string."""
    if ezo_name and ezo_name.strip():
        return ezo_name.strip()
    if configured and not is_usb_product_name(configured):
        return configured.strip()
    return fallback


def unique_id_from_serial(serial_number: str | None, device_type: str = SUPPORTED_DEVICE_TYPE) -> str:
    """Stable unique ID: FTDI serial + confirmed device type."""
    serial = (serial_number or "unknown").strip() or "unknown"
    kind = (device_type or SUPPORTED_DEVICE_TYPE).strip().lower() or "orp"
    return f"{serial}_{kind}"


def _query_line(response: EzoResponse | str, key: str) -> ParsedLine | None:
    if isinstance(response, EzoResponse):
        return response.query(key)
    for raw in _split_raw(response):
        parsed = parse_line(raw)
        if parsed.kind is LineKind.QUERY and (parsed.query_key or "").lower() == key.lower():
            return parsed
    return None


def _split_raw(raw: str) -> list[str]:
    return [part for part in re.split(r"[\r\n]+", raw) if part.strip()]


def _raw_blob(response: EzoResponse | str) -> str:
    if isinstance(response, EzoResponse):
        return "\n".join(response.raw_lines)
    return response
