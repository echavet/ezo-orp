"""Constants for the EZO Complete-ORP integration."""

from __future__ import annotations

DOMAIN = "ezo_complete"
MANUFACTURER = "Atlas Scientific"
MODEL = "EZO Complete-ORP"
DEFAULT_NAME = "EZO Complete-ORP"
DEFAULT_BAUDRATE = 9600
DEFAULT_UPDATE_INTERVAL = 5
DEFAULT_CONTINUOUS_ON_START = True
DEFAULT_CONTINUOUS_INTERVAL = 1
DEFAULT_CALIBRATION_VALUE = 225.0

# USB: FTDI virtual COM used by EZO Complete (FT230X is the usual chip).
USB_VID_FTDI = "0403"
USB_PID_FT230X = "6015"
USB_PID_FT232R = "6001"
USB_PID_FT232H = "6014"

PLATFORMS: list[str] = [
    "button",
    "number",
    "sensor",
    "switch",
    "text",
]

CONF_SERIAL_NUMBER = "serial_number"
CONF_BAUDRATE = "baudrate"
CONF_DEVICE_TYPE = "device_type"
CONF_FIRMWARE = "firmware"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CONTINUOUS_ON_START = "continuous_on_start"
CONF_CONTINUOUS_INTERVAL = "continuous_interval"

# Supported UART baud rates (EZO Baud command).
BAUDRATES: tuple[int, ...] = (300, 1200, 2400, 9600, 19200, 38400, 57600, 115200)

# Atlas EZO device type we accept after the `i` probe.
SUPPORTED_DEVICE_TYPE = "ORP"

# Command timeouts (seconds). Reading is slower than query commands.
COMMAND_TIMEOUT = 2.0
READ_COMMAND_TIMEOUT = 3.0
WAKE_SETTLE = 1.0
OPEN_SETTLE = 0.6

# Reconnect / availability.
RECONNECT_DELAY = 5.0
RAW_LINE_HISTORY = 20

# Factory-reset two-press window.
FACTORY_ARM_SECONDS = 30

# Continuous interval accepted by EZO C,<n>.
CONTINUOUS_INTERVAL_MIN = 1
CONTINUOUS_INTERVAL_MAX = 99

# ORP scale (standard vs extended).
ORP_RANGE_STANDARD = (-1020.0, 1020.0)
ORP_RANGE_EXTENDED = (-2000.0, 2000.0)

# Reset-reason codes from `Status`.
STATUS_REASON_MAP: dict[str, str] = {
    "P": "power",
    "S": "software",
    "B": "brownout",
    "W": "watchdog",
    "U": "unknown",
}

ATTRIBUTION = "Data provided by Atlas Scientific EZO Complete-ORP"
