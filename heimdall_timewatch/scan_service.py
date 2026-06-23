"""
heimdall-timewatch :: scan_service.py
Orquestación compartida entre CLI y GUI.
"""

from __future__ import annotations

import datetime
import os
import tempfile
from typing import Callable, Optional

from . import __version__
from .detector import AnalysisConfig, analyze_records
from .mft_parser import count_records, parse_mft_file
from .reporting import verdict_to_dict
from .usn_journal import build_creation_index, corroborate


ProgressCallback = Callable[[str, int], None]


def _parse_system_install(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        parsed = datetime.datetime.strptime(value, "%Y-%m-%d")
        return parsed.replace(tzinfo=datetime.timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"Fecha inválida: {value} (formato esperado YYYY-MM-DD)"
        ) from exc


def run_scan(
    mft_path: str,
    *,
    usn_path: Optional[str] = None,
    system_install: Optional[str] = None,
    min_score: int = 1,
    max_records: Optional[int] = None,
    include_directories: bool = False,
    only_in_use: bool = False,
    enable_h3: bool = True,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """Ejecuta un análisis completo y devuelve un payload serializable."""
    if not os.path.isfile(mft_path):
        raise FileNotFoundError(f"No existe el fichero MFT: {mft_path}")

    total = count_records(mft_path)
    config = AnalysisConfig(
        system_install=_parse_system_install(system_install),
        include_directories=include_directories,
        only_in_use=only_in_use,
        min_score=min_score,
        enable_h3=enable_h3,
    )

    def mft_progress(n: int) -> None:
        if progress_cb:
            progress_cb("mft", n)

    records = parse_mft_file(
        mft_path, max_records=max_records, progress_cb=mft_progress
    )
    verdicts, stats = analyze_records(records, config)

    corroborated = 0
    if usn_path:
        if os.path.isfile(usn_path):
            def usn_progress(n: int) -> None:
                if progress_cb:
                    progress_cb("usn", n)

            creation_index = build_creation_index(usn_path, progress_cb=usn_progress)
            corroborated = corroborate(verdicts, creation_index)
            stats["files_flagged"] = len(verdicts)
            stats["critical"] = sum(
                1 for v in verdicts if v.suspicion_level == "CRÍTICO"
            )
            stats["high"] = sum(1 for v in verdicts if v.suspicion_level == "ALTO")
            stats["medium"] = sum(1 for v in verdicts if v.suspicion_level == "MEDIO")
            stats["low"] = sum(1 for v in verdicts if v.suspicion_level == "BAJO")

    meta = {
        "mft_file": mft_path,
        "usn_journal": usn_path or "(no proporcionado)",
        "total_records": total,
        "corroborated_with_usn": corroborated,
        "system_install": system_install or "(no especificado)",
        "heimdall_timewatch_version": __version__,
    }

    return {
        "ok": True,
        "verdicts": verdicts,
        "stats": stats,
        "meta": meta,
        "findings": [verdict_to_dict(v) for v in verdicts],
    }


def run_lab(
    *,
    output_dir: Optional[str] = None,
    clean_files: int = 200,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """Genera y analiza un MFT de laboratorio."""
    from .labgen import generate_lab_mft

    workdir = output_dir or tempfile.mkdtemp(prefix="heimdall_lab_")
    os.makedirs(workdir, exist_ok=True)
    mft_path = os.path.join(workdir, "$MFT_lab")

    planted = generate_lab_mft(mft_path, n_clean=clean_files)

    if progress_cb:
        progress_cb("lab", 0)

    config = AnalysisConfig(min_score=1, enable_h3=True)
    records = parse_mft_file(mft_path)
    verdicts, stats = analyze_records(records, config)

    flagged_records = {v.record_number for v in verdicts}
    hits = sum(1 for rec_no, _ in planted if rec_no in flagged_records)

    meta = {
        "mode": "laboratorio",
        "mft_file": mft_path,
        "planted_cases": len(planted),
        "detected": hits,
        "heimdall_timewatch_version": __version__,
    }

    planted_info = [
        {
            "record_number": rec_no,
            "label": label,
            "detected": rec_no in flagged_records,
        }
        for rec_no, label in planted
    ]

    return {
        "ok": True,
        "verdicts": verdicts,
        "stats": stats,
        "meta": meta,
        "findings": [verdict_to_dict(v) for v in verdicts],
        "planted": planted_info,
        "lab_hits": hits,
        "lab_total": len(planted),
    }
