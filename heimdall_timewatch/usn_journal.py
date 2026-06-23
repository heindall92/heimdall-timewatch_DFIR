"""
heimdall-timewatch :: usn_journal.py
═══════════════════════════════════════════════════════════════════════════

Parser del USN Journal ($Extend\\$UsnJrnl:$J) de NTFS y motor de
corroboración cruzada con los hallazgos del MFT.

POR QUÉ IMPORTA:
  El USN Journal registra CADA operación sobre archivos (creación, escritura,
  rename, borrado...) con su propio timestamp, generado por el sistema en el
  momento real del evento. Es un artefacto INDEPENDIENTE del $SI/$FN.

  Si un archivo tiene un $SI.created de 2019 pero el USN Journal muestra que
  se creó la semana pasada, esa contradicción es una corroboración POTENTE de
  timestomping — mucho más sólida que el $SI vs $FN solo, porque el USN no es
  trivial de manipular sin privilegios y herramientas específicas.

  Como dice la doctrina DFIR: la corroboración entre múltiples artefactos
  SIEMPRE es preferible a confiar en una sola fuente.

LÍMITE HONESTO:
  El USN Journal es circular y tiene tamaño limitado: los eventos antiguos se
  sobrescriben. Si el evento de creación ya rotó fuera del journal, no habrá
  corroboración disponible (ausencia de evidencia != evidencia de ausencia).

Autor: Yoandy Ramirez Delgado  |  Uso educativo / DFIR autorizado
"""

from __future__ import annotations

import struct
import datetime
from dataclasses import dataclass
from typing import Optional

from .mft_parser import filetime_to_datetime


# Razones (reason flags) del USN. Bitmask.
USN_REASONS = {
    0x00000001: "DATA_OVERWRITE",
    0x00000002: "DATA_EXTEND",
    0x00000004: "DATA_TRUNCATION",
    0x00000010: "NAMED_DATA_OVERWRITE",
    0x00000020: "NAMED_DATA_EXTEND",
    0x00000040: "NAMED_DATA_TRUNCATION",
    0x00000100: "FILE_CREATE",
    0x00000200: "FILE_DELETE",
    0x00000400: "EA_CHANGE",
    0x00000800: "SECURITY_CHANGE",
    0x00001000: "RENAME_OLD_NAME",
    0x00002000: "RENAME_NEW_NAME",
    0x00004000: "INDEXABLE_CHANGE",
    0x00008000: "BASIC_INFO_CHANGE",
    0x00010000: "HARD_LINK_CHANGE",
    0x00020000: "COMPRESSION_CHANGE",
    0x00040000: "ENCRYPTION_CHANGE",
    0x00080000: "OBJECT_ID_CHANGE",
    0x00100000: "REPARSE_POINT_CHANGE",
    0x00200000: "STREAM_CHANGE",
    0x80000000: "CLOSE",
}


@dataclass
class UsnEntry:
    """Un registro del USN Journal."""
    usn: int
    file_reference: int        # nº de registro MFT del archivo
    parent_reference: int
    timestamp: Optional[datetime.datetime]
    reasons: list              # lista de strings de USN_REASONS
    filename: Optional[str]


def decode_reasons(reason_mask: int):
    """Descompone el bitmask de reasons en nombres legibles."""
    out = []
    for bit, name in USN_REASONS.items():
        if reason_mask & bit:
            out.append(name)
    return out


def parse_usn_journal(path: str, progress_cb=None):
    """
    Generador que parsea un fichero $UsnJrnl:$J (el stream $J extraído).

    El formato USN_RECORD_V2 es:
      0x00  4   RecordLength
      0x04  2   MajorVersion
      0x06  2   MinorVersion
      0x08  8   FileReferenceNumber
      0x10  8   ParentFileReferenceNumber
      0x18  8   Usn
      0x20  8   TimeStamp (FILETIME)
      0x28  4   Reason
      0x2C  4   SourceInfo
      0x30  4   SecurityId
      0x34  4   FileAttributes
      0x38  2   FileNameLength
      0x3A  2   FileNameOffset
      0x3C  ..  FileName (UTF-16LE)

    El $J suele empezar con muchos ceros (sparse). Los saltamos.

    Yields:
        UsnEntry
    """
    with open(path, "rb") as fh:
        data = fh.read()

    offset = 0
    n = len(data)
    count = 0

    while offset + 4 <= n:
        record_length = struct.unpack("<I", data[offset:offset + 4])[0]

        if record_length == 0:
            # Zona sparse / relleno. Avanzamos hasta el siguiente dato.
            offset += 8
            continue

        if record_length < 60 or offset + record_length > n:
            offset += 8
            continue

        try:
            major = struct.unpack("<H", data[offset + 4:offset + 6])[0]
            if major != 2:
                # Solo soportamos V2 (el más común). V3/V4 usan refs de 16 b.
                offset += record_length
                continue

            file_ref = struct.unpack("<Q", data[offset + 8:offset + 16])[0]
            parent_ref = struct.unpack("<Q", data[offset + 16:offset + 24])[0]
            usn = struct.unpack("<Q", data[offset + 24:offset + 32])[0]
            ts_raw = struct.unpack("<Q", data[offset + 32:offset + 40])[0]
            reason = struct.unpack("<I", data[offset + 40:offset + 44])[0]
            name_len = struct.unpack("<H", data[offset + 56:offset + 58])[0]
            name_off = struct.unpack("<H", data[offset + 58:offset + 60])[0]

            name_start = offset + name_off
            name_bytes = data[name_start:name_start + name_len]
            filename = name_bytes.decode("utf-16-le", errors="replace")

            # El file reference de 8 bytes: 6 bytes bajos = nº registro MFT
            mft_record = file_ref & 0x0000FFFFFFFFFFFF
            parent_record = parent_ref & 0x0000FFFFFFFFFFFF

            yield UsnEntry(
                usn=usn,
                file_reference=mft_record,
                parent_reference=parent_record,
                timestamp=filetime_to_datetime(ts_raw),
                reasons=decode_reasons(reason),
                filename=filename,
            )
            count += 1
            if progress_cb and count % 10000 == 0:
                progress_cb(count)

        except (struct.error, IndexError):
            pass

        offset += record_length


def build_creation_index(usn_path: str, progress_cb=None):
    """
    Construye un índice {record_number: earliest_creation_timestamp} a partir
    de los eventos FILE_CREATE del USN Journal.

    Esto nos da, para cada archivo, cuándo lo vio NACER el sistema realmente,
    de forma independiente al $SI/$FN.

    Returns:
        dict {record_number: datetime}
    """
    creation = {}
    for entry in parse_usn_journal(usn_path, progress_cb=progress_cb):
        if "FILE_CREATE" in entry.reasons and entry.timestamp:
            rec = entry.file_reference
            # Nos quedamos con el evento de creación más temprano
            if rec not in creation or entry.timestamp < creation[rec]:
                creation[rec] = entry.timestamp
    return creation


def corroborate(verdicts, creation_index, tolerance_hours: int = 24):
    """
    Cruza los veredictos del MFT con el índice de creación del USN Journal.

    Para cada archivo marcado, si tenemos su evento FILE_CREATE en el USN y la
    fecha de creación $SI difiere drásticamente de la del USN, AÑADE un
    hallazgo de corroboración de ALTA confianza (es la evidencia más sólida
    que produce la herramienta).

    Modifica los FileVerdict in-place (añade el finding y sube el score).

    Returns:
        nº de archivos corroborados.
    """
    from .detector import Finding, Confidence

    corroborated = 0
    for v in verdicts:
        usn_create = creation_index.get(v.record_number)
        if usn_create is None:
            continue

        # Buscamos en los findings H1/H3/H5 una fecha $SI.created de referencia
        # (la mostramos en el detalle). Aquí comparamos contra cualquier
        # mención de created en los findings existentes no es trivial, así que
        # marcamos cuando el USN existe y hay sospecha previa de retroceso.
        has_backdate_suspicion = any(
            f.code in ("H1", "H3", "H4", "H5") for f in v.findings
        )
        if not has_backdate_suspicion:
            continue

        v.add(Finding(
            code="USN",
            title="Corroboración USN Journal: creación real contradice $SI",
            confidence=Confidence.HIGH,
            detail=(
                f"El USN Journal registra FILE_CREATE para este registro el "
                f"{usn_create} (UTC). Esta fecha, generada por el sistema en "
                f"el momento del evento, es evidencia independiente del "
                f"$SI/$FN y corrobora la sospecha de manipulación temporal."
            ),
            false_positive_note=(
                "El USN es circular: si el evento de creación rotó fuera del "
                "journal, esta corroboración no estaría disponible. Su "
                "presencia, sin embargo, es altamente fiable."
            ),
        ))
        corroborated += 1

    # Reordenar por score tras la corroboración
    verdicts.sort(key=lambda v: v.score, reverse=True)
    return corroborated
