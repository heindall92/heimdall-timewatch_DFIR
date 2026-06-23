"""Tests del parser MFT: fixup, FILETIME y atributos residentes."""

from __future__ import annotations

import datetime
import struct
import tempfile
from pathlib import Path

from heimdall_timewatch.labgen import _build_record, _stamp_fixup, generate_lab_mft
from heimdall_timewatch.mft_parser import (
    MFT_RECORD_SIZE,
    apply_fixup,
    filetime_subsecond_100ns,
    filetime_to_datetime,
    parse_mft_file,
    parse_record,
)


def test_filetime_roundtrip():
    dt = datetime.datetime(2026, 6, 1, 12, 30, 45, 123456, tzinfo=datetime.timezone.utc)
    from heimdall_timewatch.labgen import dt_to_filetime

    raw = dt_to_filetime(dt)
    restored = filetime_to_datetime(raw)
    assert restored is not None
    assert restored.year == dt.year
    assert restored.month == dt.month
    assert restored.day == dt.day
    assert restored.hour == dt.hour
    assert restored.minute == dt.minute
    assert restored.second == dt.second
    assert filetime_subsecond_100ns(raw) > 0


def test_fixup_roundtrip_restores_sector_bytes():
    record = bytearray(b"\x00" * MFT_RECORD_SIZE)
    record[0:4] = b"FILE"
    usa_offset = 48
    usa_count = 3
    usn = 0x0042

    record[510:512] = b"\xAB\xCD"
    record[1022:1024] = b"\xEF\x01"

    _stamp_fixup(record, usa_offset, usa_count, usn)

    assert record[510:512] == struct.pack("<H", usn)
    assert record[1022:1024] == struct.pack("<H", usn)

    restored, warnings = apply_fixup(bytearray(record), usa_offset, usa_count)
    assert warnings == []
    assert restored[510:512] == b"\xAB\xCD"
    assert restored[1022:1024] == b"\xEF\x01"


def test_fixup_warns_on_usn_mismatch():
    record = bytearray(b"\x00" * MFT_RECORD_SIZE)
    usa_offset = 48
    usa_count = 3
    usn = 1

    record[usa_offset:usa_offset + 2] = struct.pack("<H", usn)
    record[usa_offset + 2:usa_offset + 4] = b"\xAB\xCD"
    record[usa_offset + 4:usa_offset + 6] = b"\xEF\x01"
    record[510:512] = b"\x00\x00"  # sello incorrecto (debería ser USN)

    _, warnings = apply_fixup(record, usa_offset, usa_count)
    assert any("USN mismatch" in w for w in warnings)


def test_parse_lab_record_extracts_si_and_fn():
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    times = (now, now, now, now)
    raw = _build_record(42, "test_file.txt", 5, times, times)
    rec = parse_record(raw, 42)

    assert rec is not None
    assert rec.in_use
    assert rec.filename == "test_file.txt"
    assert rec.si_present and rec.fn_present
    assert rec.si_timestamps is not None
    assert rec.fn_timestamps is not None
    assert not rec.parse_warnings


def test_lab_mft_records_have_valid_fixup():
    with tempfile.TemporaryDirectory() as tmp:
        mft_path = Path(tmp) / "$MFT_lab"
        generate_lab_mft(str(mft_path), n_clean=5)
        records = list(parse_mft_file(str(mft_path)))
        planted = [r for r in records if r.filename and "documento_" not in r.filename]

        assert len(planted) >= 6
        for rec in planted:
            assert not any("USN mismatch" in w for w in rec.parse_warnings), rec.filename


def test_parse_mft_file_yields_expected_count():
    with tempfile.TemporaryDirectory() as tmp:
        mft_path = Path(tmp) / "$MFT_lab"
        generate_lab_mft(str(mft_path), n_clean=10)
        records = list(parse_mft_file(str(mft_path)))
        assert len(records) == 16 + 10 + 6
