"""Runtime state for one EZO Complete-ORP device."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EzoDeviceState:
    """Snapshot consumed by entities and diagnostics."""

    orp: float | None = None
    continuous: bool | None = None
    continuous_interval: int | None = None
    led: bool | None = None
    calibrated: bool | None = None
    firmware: str | None = None
    device_type: str | None = None
    device_name: str | None = None
    status_reason: str | None = None
    status_reason_code: str | None = None
    status_voltage: float | None = None
    orp_extended: bool | None = None
    response_codes: bool | None = None
    sleeping: bool = False
    last_raw: str | None = None
    last_lines: list[str] = field(default_factory=list)
    export_data: str | None = None
    factory_armed: bool = False
    port: str | None = None
    baudrate: int | None = None
    serial_number: str | None = None

    def copy(self) -> EzoDeviceState:
        """Shallow copy with a new last_lines list."""
        return EzoDeviceState(
            orp=self.orp,
            continuous=self.continuous,
            continuous_interval=self.continuous_interval,
            led=self.led,
            calibrated=self.calibrated,
            firmware=self.firmware,
            device_type=self.device_type,
            device_name=self.device_name,
            status_reason=self.status_reason,
            status_reason_code=self.status_reason_code,
            status_voltage=self.status_voltage,
            orp_extended=self.orp_extended,
            response_codes=self.response_codes,
            sleeping=self.sleeping,
            last_raw=self.last_raw,
            last_lines=list(self.last_lines),
            export_data=self.export_data,
            factory_armed=self.factory_armed,
            port=self.port,
            baudrate=self.baudrate,
            serial_number=self.serial_number,
        )
