"""Unit tests for the EZO UART parser (no Home Assistant, no serialx)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "ezo_complete"


def _load(name: str, path: Path):
    """Load a module under the ezo_complete package without importing __init__.py."""
    if "ezo_complete" not in sys.modules:
        pkg = types.ModuleType("ezo_complete")
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules["ezo_complete"] = pkg
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


const = _load("ezo_complete.const", PKG_DIR / "const.py")
protocol = _load("ezo_complete.protocol", PKG_DIR / "protocol.py")


def test_encode_command() -> None:
    assert protocol.encode_command("i") == b"i\r"
    assert protocol.encode_command("Cal,225") == b"Cal,225\r"


def test_parse_reading() -> None:
    line = protocol.parse_line("225.4")
    assert line.kind is protocol.LineKind.READING
    assert line.value == 225.4
    line = protocol.parse_line("-150.2")
    assert line.value == -150.2


def test_parse_status_codes() -> None:
    ok = protocol.parse_line("*OK")
    assert ok.kind is protocol.LineKind.STATUS
    assert ok.status_code == "OK"
    err = protocol.parse_line("*ER")
    assert err.status_code == "ER"


def test_parse_device_info_orp() -> None:
    info = protocol.parse_device_info("?i,ORP,1.98")
    assert info is not None
    assert info.is_orp
    assert info.device_type == "ORP"
    assert info.firmware == "1.98"
    assert protocol.is_orp_info_response("?i,ORP,2.10\r*OK")


def test_reject_other_ezo() -> None:
    info = protocol.parse_device_info("?i,pH,2.14")
    assert info is not None
    assert not info.is_orp
    assert not protocol.is_orp_info_response("?i,EC,2.10")


def test_parse_status() -> None:
    status = protocol.parse_status("?Status,P,5.038")
    assert status is not None
    assert status.reason_code == "P"
    assert status.reason == "power"
    assert status.voltage == 5.038
    brown = protocol.parse_status("?Status,B,4.91")
    assert brown is not None
    assert brown.reason == "brownout"


def test_parse_continuous() -> None:
    off = protocol.parse_continuous("?C,0")
    assert off is not None and off.enabled is False
    on = protocol.parse_continuous("?C,1")
    assert on is not None and on.enabled is True and on.interval == 1
    period = protocol.parse_continuous("?C,5")
    assert period is not None and period.enabled is True and period.interval == 5


def test_parse_cal_led_name_flags() -> None:
    assert protocol.parse_calibrated("?Cal,1") is True
    assert protocol.parse_calibrated("?Cal,0") is False
    assert protocol.parse_led("?L,1") is True
    assert protocol.parse_led("?L,0") is False
    assert protocol.parse_name("?Name,pool") == "pool"
    assert protocol.parse_flag("?ORPext,1", "orpext") is True
    assert protocol.parse_flag("?OK,0", "ok") is False


def test_ezo_response_ok() -> None:
    response = protocol.EzoResponse(
        command="R",
        lines=[
            protocol.parse_line("650.2"),
            protocol.parse_line("*OK"),
        ],
    )
    assert response.ok
    assert response.first_reading() == 650.2
    bad = protocol.EzoResponse(
        command="Nope",
        lines=[protocol.parse_line("*ER")],
    )
    assert not bad.ok
    assert bad.error_code == "ER"


def test_unique_id() -> None:
    assert protocol.unique_id_from_serial("FT123456") == "FT123456_orp"
    assert protocol.unique_id_from_serial(None) == "unknown_orp"


def test_export_count() -> None:
    assert protocol.parse_export_count("?EXPORT,6") == 6


def test_response_code_aliases() -> None:
    assert protocol.parse_flag("?OK,1", "ok") is True
    assert protocol.parse_flag("?O,1", "o") is True
    assert protocol.parse_flag("?RESPONSE,0", "response") is False
    assert "RESPONSE,1" in const.RESPONSE_CODE_ENABLE_COMMANDS
    assert "OK,1" in const.RESPONSE_CODE_ENABLE_COMMANDS


def test_response_from_collected_i() -> None:
    response = protocol.EzoResponse(
        command="i",
        lines=[
            protocol.parse_line("?i,ORP,1.98"),
            protocol.parse_line("*OK"),
        ],
    )
    info = protocol.parse_device_info(response)
    assert info is not None
    assert info.is_orp
    assert info.firmware == "1.98"
