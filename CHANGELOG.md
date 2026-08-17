# Changelog

All notable changes to this project will be documented in this file.

Versioning follows **CalVer** `YYYY.M.D` (date-based, same spirit as Home Assistant Core), e.g. `2026.8.19`.

## [2026.8.19] - 2026-08-17

### Fixed

- Calibration buttons now stop continuous mode (`C,0`) before `Cal,<mv>` / `Cal,?`, force an `R` so ORP updates immediately, parse `?Cal,0/1` even in a mixed stream, and show a persistent notification (success or `*ER` / timeout).
- Device name no longer uses the FTDI product string (`FT230X Basic UART`); it uses the EZO `Name` register or **EZO ORP**.
- Factory reset no longer fails re-identify on leftover continuous readings (`323.1 | 323.0`): `C,0`, drain, retry `i`.

## [2026.8.18] - 2026-08-17

### Fixed

- Setup no longer fails when `OK,1` returns `*ER`. Response-code framing is firmware-dependent (`RESPONSE,1` / `O,1` / `OK,1`); all three are tried and ignored if unsupported. Continuous stream is stopped before the remaining init queries.

## [2026.8.17] - 2026-08-17

### Added

- Initial HACS custom integration for the **Atlas Scientific EZO Complete-ORP**.
- USB discovery (FTDI VID `0403` + PID `6015` / `6001` / `6014`) with mandatory `i` probe (ORP only).
- Config Flow + Options Flow + reconfigure flow, multi-device, stable unique ID (`{ftdi_serial}_orp`).
- serialx UART client, `DataUpdateCoordinator`, `runtime_data`, hotplug reconnect.
- Entities: ORP sensor, continuous + LED + ORPext switches, calibration buttons/number, Find / Sleep / factory / export, diagnostics sensors, optional device name.
- Services: `send_command`, `factory_reset` (confirm), `export_calibration`, `import_calibration`.
- FR/EN translations, diagnostics dump, local brand assets, unit tests for the EZO parser.

[2026.8.19]: https://github.com/echavet/ezo-orp/releases/tag/2026.8.19
[2026.8.18]: https://github.com/echavet/ezo-orp/releases/tag/2026.8.18
[2026.8.17]: https://github.com/echavet/ezo-orp/releases/tag/2026.8.17
