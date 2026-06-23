"""
heimdall-timewatch :: mft_parser.py
═══════════════════════════════════════════════════════════════════════════

Parser de bajo nivel del Master File Table (MFT) de NTFS.

Lee registros FILE de 1024 bytes, extrae los atributos $STANDARD_INFORMATION
(0x10) y $FILE_NAME (0x30), y decodifica los 8 timestamps MACE (4 en cada
atributo) almacenados como FILETIME de 64 bits (nanosegundos*100 desde
1601-01-01 UTC).

Este módulo NO juzga. Solo extrae datos crudos y fiables. El veredicto de
timestomping lo da el motor de detección (detector.py) sobre estos datos.

Autor: Heindall  |  Uso educativo / DFIR autorizado
Referencia: Brian Carrier "File System Forensic Analysis" + Microsoft NTFS docs
"""

from __future__ import annotations

import struct
import datetime
from dataclasses import dataclass, field
from typing import Optional


# ───────────────────────────────────────────────────────────────────────────
# Constantes del formato NTFS
# ───────────────────────────────────────────────────────────────────────────

MFT_RECORD_SIZE = 1024          # Tamaño estándar de un registro FILE
FILE_SIGNATURE = b"FILE"        # Firma al inicio de cada registro válido
BAAD_SIGNATURE = b"BAAD"        # Registro corrupto marcado por chkdsk

# Tipos de atributo que nos interesan
ATTR_STANDARD_INFORMATION = 0x10
ATTR_FILE_NAME = 0x30

# Flags del header del registro
FLAG_IN_USE = 0x01              # El registro está en uso (archivo existe)
FLAG_DIRECTORY = 0x02           # El registro es un directorio

# Namespaces del atributo $FILE_NAME
FN_NAMESPACE = {
    0: "POSIX",
    1: "Win32",
    2: "DOS",
    3: "Win32&DOS",
}

# Epoch de FILETIME: 1601-01-01 00:00:00 UTC, en intervalos de 100 ns
# Diferencia con epoch Unix (1970) en segundos
FILETIME_EPOCH_DIFF = 11644473600


# ───────────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class MaceTimestamps:
    """Los 4 timestamps MACE de un atributo (SI o FN)."""
    created: Optional[datetime.datetime] = None    # M -> birth/creation
    modified: Optional[datetime.datetime] = None   # A -> last modified (data)
    mft_modified: Optional[datetime.datetime] = None  # C -> MFT entry changed
    accessed: Optional[datetime.datetime] = None   # E -> last accessed

    # Guardamos también los valores crudos para análisis de precisión
    created_raw: int = 0
    modified_raw: int = 0
    mft_modified_raw: int = 0
    accessed_raw: int = 0

    def as_list(self):
        return [
            ("created", self.created, self.created_raw),
            ("modified", self.modified, self.modified_raw),
            ("mft_modified", self.mft_modified, self.mft_modified_raw),
            ("accessed", self.accessed, self.accessed_raw),
        ]


@dataclass
class MftRecord:
    """Un registro del MFT, ya parseado."""
    record_number: int
    in_use: bool
    is_directory: bool
    sequence_number: int

    filename: Optional[str] = None
    filename_namespace: Optional[str] = None
    parent_ref: Optional[int] = None

    si_timestamps: Optional[MaceTimestamps] = None
    fn_timestamps: Optional[MaceTimestamps] = None

    # Tamaños declarados (útiles como corroboración secundaria)
    si_present: bool = False
    fn_present: bool = False

    flags_raw: int = 0
    parse_warnings: list = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────────
# Helpers de decodificación
# ───────────────────────────────────────────────────────────────────────────

def filetime_to_datetime(raw: int) -> Optional[datetime.datetime]:
    """
    Convierte un FILETIME de 64 bits (intervalos de 100 ns desde 1601-01-01)
    a un datetime UTC. Devuelve None si el valor es 0 o inválido.
    """
    if raw == 0:
        return None
    try:
        # raw está en intervalos de 100 ns. Pasamos a segundos.
        seconds_since_1601 = raw / 10_000_000
        unix_seconds = seconds_since_1601 - FILETIME_EPOCH_DIFF
        # Rango razonable: 1601..2200 aprox. Filtra basura.
        if unix_seconds < -FILETIME_EPOCH_DIFF or unix_seconds > 7258118400:
            return None
        return datetime.datetime.fromtimestamp(
            unix_seconds, tz=datetime.timezone.utc
        )
    except (OverflowError, OSError, ValueError):
        return None


def filetime_subsecond_100ns(raw: int) -> int:
    """
    Devuelve la parte sub-segundo de un FILETIME, en intervalos de 100 ns.
    Si es 0, el timestamp tiene precisión "redonda" al segundo -> indicador
    clásico (aunque no concluyente) de manipulación por herramienta automática.
    """
    if raw == 0:
        return 0
    return raw % 10_000_000


def apply_fixup(record: bytearray, usa_offset: int, usa_count: int) -> bytearray:
    """
    Aplica el Update Sequence Array (fixup) de NTFS.

    NTFS reemplaza los últimos 2 bytes de cada sector (512 b) del registro por
    un valor de chequeo (el USN), guardando los bytes reales en el USA. Hay que
    restaurarlos antes de parsear, o los datos de los límites de sector estarán
    corruptos.
    """
    if usa_count == 0:
        return record

    # El primer USHORT del USA es el número de secuencia (el que se escribió
    # al final de cada sector). Los siguientes son los valores originales.
    usn = record[usa_offset:usa_offset + 2]
    fixup_values = []
    for i in range(1, usa_count):
        off = usa_offset + (i * 2)
        fixup_values.append(record[off:off + 2])

    # Cada sector de 512 bytes: sus 2 últimos bytes se restauran
    for i, original in enumerate(fixup_values):
        sector_end = (i + 1) * 512
        if sector_end <= len(record):
            # Verificación de integridad: los 2 últimos bytes del sector
            # deberían coincidir con el USN. Si no, el registro está dañado.
            record[sector_end - 2:sector_end] = original

    return record


# ───────────────────────────────────────────────────────────────────────────
# Parsing de atributos
# ───────────────────────────────────────────────────────────────────────────

def _parse_standard_information(data: bytes) -> MaceTimestamps:
    """
    $STANDARD_INFORMATION (0x10). Los 4 timestamps están en los primeros
    32 bytes del contenido del atributo: created, modified, mft_modified,
    accessed. Cada uno es un FILETIME de 8 bytes little-endian.
    """
    ts = MaceTimestamps()
    if len(data) < 32:
        return ts

    created_raw, modified_raw, mft_raw, accessed_raw = struct.unpack(
        "<QQQQ", data[0:32]
    )
    ts.created_raw = created_raw
    ts.modified_raw = modified_raw
    ts.mft_modified_raw = mft_raw
    ts.accessed_raw = accessed_raw

    ts.created = filetime_to_datetime(created_raw)
    ts.modified = filetime_to_datetime(modified_raw)
    ts.mft_modified = filetime_to_datetime(mft_raw)
    ts.accessed = filetime_to_datetime(accessed_raw)
    return ts


def _parse_file_name(data: bytes):
    """
    $FILE_NAME (0x30). Estructura del contenido:
      0x00  8 bytes  parent directory reference (6 bytes ref + 2 seq)
      0x08  8 bytes  created (FILETIME)
      0x10  8 bytes  modified
      0x18  8 bytes  mft_modified
      0x20  8 bytes  accessed
      0x28  8 bytes  allocated size
      0x30  8 bytes  real size
      0x38  4 bytes  flags
      0x3C  4 bytes  reparse
      0x40  1 byte   filename length (en caracteres)
      0x41  1 byte   filename namespace
      0x42  ...      filename (UTF-16LE)

    Devuelve (MaceTimestamps, filename, namespace, parent_ref).
    """
    ts = MaceTimestamps()
    if len(data) < 66:
        return ts, None, None, None

    parent_raw = struct.unpack("<Q", data[0:8])[0]
    parent_ref = parent_raw & 0x0000FFFFFFFFFFFF  # 6 bytes bajos

    created_raw, modified_raw, mft_raw, accessed_raw = struct.unpack(
        "<QQQQ", data[8:40]
    )
    ts.created_raw = created_raw
    ts.modified_raw = modified_raw
    ts.mft_modified_raw = mft_raw
    ts.accessed_raw = accessed_raw
    ts.created = filetime_to_datetime(created_raw)
    ts.modified = filetime_to_datetime(modified_raw)
    ts.mft_modified = filetime_to_datetime(mft_raw)
    ts.accessed = filetime_to_datetime(accessed_raw)

    name_length = data[64]
    namespace_id = data[65]
    namespace = FN_NAMESPACE.get(namespace_id, f"unknown({namespace_id})")

    name_bytes = data[66:66 + (name_length * 2)]
    try:
        filename = name_bytes.decode("utf-16-le", errors="replace")
    except Exception:
        filename = None

    return ts, filename, namespace, parent_ref


# ───────────────────────────────────────────────────────────────────────────
# Parsing del registro completo
# ───────────────────────────────────────────────────────────────────────────

def parse_record(raw: bytes, record_number: int) -> Optional[MftRecord]:
    """
    Parsea un único registro FILE de 1024 bytes. Devuelve un MftRecord o None
    si el registro no es válido / está vacío.

    Cuando un archivo tiene varios nombres (p.ej. Win32 + DOS 8.3), nos
    quedamos con el atributo $FILE_NAME del namespace de mayor prioridad
    (Win32 / Win32&DOS / POSIX antes que el corto DOS), porque es el que
    refleja el nombre real y sus timestamps de kernel.
    """
    if len(raw) < 48:
        return None

    signature = raw[0:4]
    if signature == BAAD_SIGNATURE:
        rec = MftRecord(record_number=record_number, in_use=False,
                        is_directory=False, sequence_number=0)
        rec.parse_warnings.append("Registro marcado BAAD (corrupto por chkdsk)")
        return rec
    if signature != FILE_SIGNATURE:
        return None  # Registro vacío o no inicializado

    record = bytearray(raw)

    # Header del registro FILE
    usa_offset = struct.unpack("<H", record[4:6])[0]
    usa_count = struct.unpack("<H", record[6:8])[0]
    seq_number = struct.unpack("<H", record[16:18])[0]
    first_attr_offset = struct.unpack("<H", record[20:22])[0]
    flags = struct.unpack("<H", record[22:24])[0]

    # Aplicar fixup (restaurar bytes de los límites de sector)
    try:
        record = apply_fixup(record, usa_offset, usa_count)
    except Exception:
        pass  # Si el fixup falla, intentamos parsear igualmente

    in_use = bool(flags & FLAG_IN_USE)
    is_directory = bool(flags & FLAG_DIRECTORY)

    rec = MftRecord(
        record_number=record_number,
        in_use=in_use,
        is_directory=is_directory,
        sequence_number=seq_number,
        flags_raw=flags,
    )

    # Recorrer la cadena de atributos
    offset = first_attr_offset
    best_fn_priority = -1  # Para elegir el mejor $FILE_NAME

    # Prioridad de namespace (mayor = mejor nombre "real")
    ns_priority = {"Win32&DOS": 3, "Win32": 2, "POSIX": 1, "DOS": 0}

    safety = 0
    while offset + 8 <= len(record) and safety < 64:
        safety += 1
        attr_type = struct.unpack("<I", record[offset:offset + 4])[0]

        if attr_type == 0xFFFFFFFF:  # Marca de fin de atributos
            break

        attr_length = struct.unpack("<I", record[offset + 4:offset + 8])[0]
        if attr_length == 0 or offset + attr_length > len(record):
            break

        non_resident = record[offset + 8]

        if non_resident == 0:  # Atributo residente (los SI y FN lo son)
            content_size = struct.unpack(
                "<I", record[offset + 16:offset + 20]
            )[0]
            content_offset = struct.unpack(
                "<H", record[offset + 20:offset + 22]
            )[0]
            content_start = offset + content_offset
            content = record[content_start:content_start + content_size]

            if attr_type == ATTR_STANDARD_INFORMATION:
                rec.si_timestamps = _parse_standard_information(bytes(content))
                rec.si_present = True

            elif attr_type == ATTR_FILE_NAME:
                fn_ts, fname, ns, parent = _parse_file_name(bytes(content))
                prio = ns_priority.get(ns, 0)
                # Nos quedamos con el nombre de mayor prioridad
                if prio > best_fn_priority:
                    best_fn_priority = prio
                    rec.fn_timestamps = fn_ts
                    rec.filename = fname
                    rec.filename_namespace = ns
                    rec.parent_ref = parent
                    rec.fn_present = True

        offset += attr_length

    return rec


# ───────────────────────────────────────────────────────────────────────────
# Lectura del fichero MFT completo
# ───────────────────────────────────────────────────────────────────────────

def parse_mft_file(path: str, max_records: Optional[int] = None,
                   progress_cb=None):
    """
    Generador que lee un fichero $MFT (extraído con FTK Imager, MFTECmd,
    icat, etc.) y produce MftRecord uno a uno.

    Args:
        path: ruta al fichero $MFT crudo.
        max_records: limita el nº de registros (para pruebas).
        progress_cb: callback(records_leidos) para mostrar progreso.

    Yields:
        MftRecord
    """
    with open(path, "rb") as fh:
        record_number = 0
        while True:
            raw = fh.read(MFT_RECORD_SIZE)
            if len(raw) < MFT_RECORD_SIZE:
                break

            rec = parse_record(raw, record_number)
            if rec is not None:
                yield rec

            record_number += 1
            if progress_cb and record_number % 5000 == 0:
                progress_cb(record_number)
            if max_records and record_number >= max_records:
                break


def count_records(path: str) -> int:
    """Cuenta cuántos registros (de 1024 b) tiene el fichero MFT."""
    import os
    size = os.path.getsize(path)
    return size // MFT_RECORD_SIZE
