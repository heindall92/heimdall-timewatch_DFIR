"""
heimdall-timewatch :: labgen.py
═══════════════════════════════════════════════════════════════════════════

Generador de un fichero $MFT SINTÉTICO con casos de timestomping conocidos,
para que puedas probar y estudiar el detector SIN necesitar extraer un MFT
real de un sistema Windows.

Construye registros FILE de 1024 bytes válidos (con sus atributos $SI y $FN)
e introduce, de forma controlada y etiquetada, varios escenarios:

  · Archivos limpios (timestamps coherentes, subsegundos realistas)
  · Timestomping clásico ($SI retrocedido respecto a $FN)
  · Precisión redondeada al segundo (herramienta automática)
  · created posterior a modified (imposible lógico)
  · Fecha en el futuro
  · $FN con subsegundos en cero (manipulación avanzada)

Esto es el "DVWA del timestomping": un campo de tiro seguro y reproducible.

Autor: Yoandy Ramirez Delgado  |  Uso educativo / DFIR autorizado
"""

from __future__ import annotations

import struct
import random
import datetime

from .mft_parser import (
    MFT_RECORD_SIZE, FILETIME_EPOCH_DIFF,
    ATTR_STANDARD_INFORMATION, ATTR_FILE_NAME,
)


def dt_to_filetime(dt: datetime.datetime, force_zero_subsec: bool = False) -> int:
    """Convierte un datetime UTC a FILETIME (100 ns desde 1601)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    unix = dt.timestamp()
    ft = int((unix + FILETIME_EPOCH_DIFF) * 10_000_000)
    if force_zero_subsec:
        ft = (ft // 10_000_000) * 10_000_000  # trunca subsegundos a cero
    else:
        # Añadimos subsegundos realistas (ruido fino) si no los tiene
        if ft % 10_000_000 == 0:
            ft += random.randint(1, 9_999_999)
    return ft


def _build_si_attribute(created, modified, mft_mod, accessed,
                        zero_subsec=False):
    """Construye un atributo $STANDARD_INFORMATION residente."""
    content = struct.pack(
        "<QQQQ",
        dt_to_filetime(created, zero_subsec),
        dt_to_filetime(modified, zero_subsec),
        dt_to_filetime(mft_mod, zero_subsec),
        dt_to_filetime(accessed, zero_subsec),
    )
    # Resto del $SI (flags, version, etc.) lo rellenamos a 48 bytes
    content += b"\x00" * (48 - len(content))

    return _wrap_resident_attribute(ATTR_STANDARD_INFORMATION, content)


def _build_fn_attribute(filename, parent_ref, created, modified, mft_mod,
                        accessed, zero_subsec=False):
    """Construye un atributo $FILE_NAME residente (namespace Win32)."""
    name_utf16 = filename.encode("utf-16-le")
    name_len_chars = len(filename)

    content = struct.pack("<Q", parent_ref)  # parent reference
    content += struct.pack(
        "<QQQQ",
        dt_to_filetime(created, zero_subsec),
        dt_to_filetime(modified, zero_subsec),
        dt_to_filetime(mft_mod, zero_subsec),
        dt_to_filetime(accessed, zero_subsec),
    )
    content += struct.pack("<Q", 0)   # allocated size
    content += struct.pack("<Q", 0)   # real size
    content += struct.pack("<I", 0)   # flags
    content += struct.pack("<I", 0)   # reparse
    content += struct.pack("<B", name_len_chars)  # name length
    content += struct.pack("<B", 1)   # namespace 1 = Win32
    content += name_utf16

    return _wrap_resident_attribute(ATTR_FILE_NAME, content)


def _wrap_resident_attribute(attr_type: int, content: bytes) -> bytes:
    """Envuelve el contenido en una cabecera de atributo residente."""
    content_len = len(content)
    # Cabecera residente = 24 bytes (con name_length=0)
    header_size = 24
    # El contenido empieza tras la cabecera; alineamos el total a 8 bytes
    total = header_size + content_len
    padding = (8 - (total % 8)) % 8
    total_padded = total + padding

    header = struct.pack("<I", attr_type)         # tipo
    header += struct.pack("<I", total_padded)     # longitud total
    header += struct.pack("<B", 0)                # non-resident = 0
    header += struct.pack("<B", 0)                # name length
    header += struct.pack("<H", 0)                # name offset
    header += struct.pack("<H", 0)                # flags
    header += struct.pack("<H", 0)                # attribute id
    header += struct.pack("<I", content_len)      # content size
    header += struct.pack("<H", header_size)      # content offset
    header += struct.pack("<H", 0)                # indexed flag

    return header + content + (b"\x00" * padding)


def _stamp_fixup(record: bytearray, usa_offset: int, usa_count: int, usn: int) -> None:
    """Escribe el USN en los límites de sector y guarda los bytes originales en USA."""
    usn_bytes = struct.pack("<H", usn)
    record[usa_offset:usa_offset + 2] = usn_bytes
    for i in range(1, usa_count):
        sector_end = i * 512
        if sector_end <= len(record):
            usa_entry = usa_offset + (i * 2)
            record[usa_entry:usa_entry + 2] = record[sector_end - 2:sector_end]
            record[sector_end - 2:sector_end] = usn_bytes


def _build_record(record_number: int, filename: str, parent_ref: int,
                  si_times, fn_times, is_directory=False,
                  si_zero_subsec=False, fn_zero_subsec=False) -> bytes:
    """
    Construye un registro FILE completo de 1024 bytes.

    si_times / fn_times: tuplas (created, modified, mft_mod, accessed).
    """
    si_attr = _build_si_attribute(*si_times, zero_subsec=si_zero_subsec)
    fn_attr = _build_fn_attribute(filename, parent_ref, *fn_times,
                                  zero_subsec=fn_zero_subsec)

    attrs = si_attr + fn_attr
    end_marker = struct.pack("<I", 0xFFFFFFFF) + struct.pack("<I", 0)

    # Cabecera del registro FILE (48 bytes)
    flags = 0x01  # in use
    if is_directory:
        flags |= 0x02

    first_attr_offset = 56  # tras cabecera + USA

    header = b"FILE"                              # firma
    header += struct.pack("<H", 48)               # offset USA
    header += struct.pack("<H", 3)                # USA count
    header += struct.pack("<Q", 0)                # LSN
    header += struct.pack("<H", 1)                # sequence number
    header += struct.pack("<H", 1)                # link count
    header += struct.pack("<H", first_attr_offset)  # offset 1er atributo
    header += struct.pack("<H", flags)            # flags
    used = first_attr_offset + len(attrs) + len(end_marker)
    header += struct.pack("<I", used)             # bytes usados
    header += struct.pack("<I", MFT_RECORD_SIZE)  # bytes asignados
    header += struct.pack("<Q", 0)                # base record ref
    header += struct.pack("<H", 4)                # next attribute id
    header += struct.pack("<H", 0)                # padding
    header += struct.pack("<I", record_number)    # nº de registro

    # USA (Update Sequence Array): USN + valores por sector.
    seq_number = 1
    usa_count = 3
    usa = struct.pack("<H", seq_number)
    usa += struct.pack("<H", 0)
    usa += struct.pack("<H", 0)

    body = header + usa
    # Alineamos hasta first_attr_offset
    body += b"\x00" * (first_attr_offset - len(body))
    body += attrs + end_marker

    # Rellenar hasta 1024 bytes
    body += b"\x00" * (MFT_RECORD_SIZE - len(body))
    record = bytearray(body[:MFT_RECORD_SIZE])
    _stamp_fixup(record, usa_offset=48, usa_count=usa_count, usn=seq_number)
    return bytes(record)


def generate_lab_mft(output_path: str, n_clean: int = 200):
    """
    Genera un fichero $MFT de laboratorio con n_clean archivos limpios más
    6 casos de timestomping etiquetados.

    Devuelve una lista de (record_number, etiqueta) de los casos plantados,
    para que puedas verificar que el detector los encuentra.
    """
    now = datetime.datetime(2026, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    base = datetime.datetime(2025, 1, 1, 9, 0, 0, tzinfo=datetime.timezone.utc)

    records = []
    planted = []
    rec_no = 0

    # ── Registros 0-15: simulamos los metadatos del sistema (sin interés) ──
    for i in range(16):
        t = base + datetime.timedelta(seconds=i)
        times = (t, t, t, t)
        records.append(_build_record(
            rec_no, f"$Meta{i}", 5, times, times, is_directory=False))
        rec_no += 1

    # ── Archivos LIMPIOS: $SI y $FN coherentes, fechas crecientes ──
    for i in range(n_clean):
        created = base + datetime.timedelta(hours=i)
        modified = created + datetime.timedelta(minutes=random.randint(1, 600))
        accessed = modified + datetime.timedelta(minutes=random.randint(0, 60))
        mft_mod = modified
        si = (created, modified, mft_mod, accessed)
        # En un archivo limpio, $FN suele ser igual o muy próximo a $SI
        fn = (created, created, created, created)
        records.append(_build_record(
            rec_no, f"documento_{i:03d}.txt", 5, si, fn))
        rec_no += 1

    # ── CASO 1: Timestomping clásico ($SI muy anterior a $FN) ──
    # El archivo se creó de verdad en 2026 (lo dice $FN), pero el atacante
    # retrocedió el $SI a 2019 para esconderlo.
    fn_create = datetime.datetime(2026, 5, 28, 14, 30, 0,
                                  tzinfo=datetime.timezone.utc)
    si_fake = datetime.datetime(2019, 3, 15, 10, 0, 0,
                                tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "evil_backdoor.exe", 5,
        si_times=(si_fake, si_fake, fn_create, si_fake),
        fn_times=(fn_create, fn_create, fn_create, fn_create)))
    planted.append((rec_no, "H1: timestomping clásico ($SI<$FN)"))
    rec_no += 1

    # ── CASO 2: Precisión redondeada al segundo (herramienta automática) ──
    t2 = datetime.datetime(2026, 5, 20, 8, 0, 0, tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "mimikatz_renamed.exe", 5,
        si_times=(t2, t2, t2, t2),
        fn_times=(t2, t2, t2, t2),
        si_zero_subsec=True))   # subsegundos a cero en $SI
    planted.append((rec_no, "H2: subsegundos $SI en cero"))
    rec_no += 1

    # ── CASO 3: created posterior a modified (imposible lógico) ──
    created3 = datetime.datetime(2026, 5, 25, 16, 0, 0,
                                 tzinfo=datetime.timezone.utc)
    modified3 = datetime.datetime(2026, 5, 25, 10, 0, 0,  # ¡antes de crear!
                                  tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "tampered_config.dll", 5,
        si_times=(created3, modified3, created3, created3),
        fn_times=(created3, modified3, created3, created3)))
    planted.append((rec_no, "H4: created > modified"))
    rec_no += 1

    # ── CASO 4: Fecha en el futuro ──
    future = datetime.datetime(2030, 1, 1, 0, 0, 0,
                               tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "future_file.bin", 5,
        si_times=(future, future, future, future),
        fn_times=(future, future, future, future)))
    planted.append((rec_no, "H5: fecha en el futuro"))
    rec_no += 1

    # ── CASO 5: $FN con subsegundos en cero (manipulación avanzada) ──
    t5 = datetime.datetime(2026, 4, 10, 11, 0, 0, tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "setmace_victim.sys", 5,
        si_times=(t5, t5, t5, t5),
        fn_times=(t5, t5, t5, t5),
        fn_zero_subsec=True))   # subsegundos a cero en $FN (raro)
    planted.append((rec_no, "H6: subsegundos $FN en cero"))
    rec_no += 1

    # ── CASO 6: combinado (clásico + redondeo) - score alto ──
    fn_c6 = datetime.datetime(2026, 5, 30, 9, 0, 0, tzinfo=datetime.timezone.utc)
    si_c6 = datetime.datetime(2020, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    records.append(_build_record(
        rec_no, "rootkit.dat", 5,
        si_times=(si_c6, si_c6, fn_c6, si_c6),
        fn_times=(fn_c6, fn_c6, fn_c6, fn_c6),
        si_zero_subsec=True))
    planted.append((rec_no, "H1+H2: combinado (clásico + redondeo)"))
    rec_no += 1

    # Escribir el fichero MFT
    with open(output_path, "wb") as fh:
        for r in records:
            fh.write(r)

    return planted
