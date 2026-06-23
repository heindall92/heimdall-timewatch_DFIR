"""
heimdall-timewatch
══════════════════
Detector de timestomping en NTFS mediante comparación $STANDARD_INFORMATION
vs $FILE_NAME y corroboración cruzada con el USN Journal.

Creado por Yoandy Ramirez Delgado · uso educativo / DFIR autorizado.
"""

__version__ = "1.0.0"
__author__ = "Yoandy Ramirez Delgado"

from .mft_parser import parse_mft_file, parse_record, MftRecord, count_records
from .detector import analyze_records, AnalysisConfig, FileVerdict, Finding
from .usn_journal import build_creation_index, corroborate

__all__ = [
    "parse_mft_file",
    "parse_record",
    "MftRecord",
    "count_records",
    "analyze_records",
    "AnalysisConfig",
    "FileVerdict",
    "Finding",
    "build_creation_index",
    "corroborate",
]
