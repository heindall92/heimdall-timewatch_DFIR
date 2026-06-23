"""Tests del modo laboratorio — verificación 6/6 casos plantados."""

from __future__ import annotations

from heimdall_timewatch.scan_service import run_lab


def test_run_lab_detects_all_planted_cases():
    result = run_lab(clean_files=50)

    assert result["ok"] is True
    assert result["lab_total"] == 6
    assert result["lab_hits"] == 6, (
        f"Esperado 6/6; detectados {result['lab_hits']}/6. "
        f"Plantados: {result['planted']}"
    )

    for case in result["planted"]:
        assert case["detected"], f"No detectado: MFT #{case['record_number']} — {case['label']}"
