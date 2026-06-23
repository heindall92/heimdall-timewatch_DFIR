#!/usr/bin/env python3
"""
heimdall-timewatch :: cli.py
═══════════════════════════════════════════════════════════════════════════

Interfaz de línea de comandos. Orquesta el parsing del MFT, la detección, la
corroboración con USN Journal y la generación de informes.

Subcomandos:
  scan      Analiza un fichero $MFT (y opcionalmente un $UsnJrnl:$J)
  lab       Genera un MFT de laboratorio con casos plantados y lo analiza
  parse     Vuelca los timestamps de un MFT a CSV (sin juzgar)

Ejemplos:
  python -m heimdall_timewatch.cli lab
  python -m heimdall_timewatch.cli scan -m \\$MFT --usn \\$J --html informe.html
  python -m heimdall_timewatch.cli scan -m \\$MFT --json out.json --min-score 25

Autor: Heindall  |  Uso educativo / DFIR autorizado
"""

from __future__ import annotations

import sys
import os
import argparse
import datetime
import tempfile

from . import __version__
from .mft_parser import parse_mft_file, count_records
from .detector import analyze_records, AnalysisConfig
from .usn_journal import build_creation_index, corroborate
from .reporting import (
    print_banner, print_console_report,
    export_json, export_csv, export_html, C,
)


def _parse_date(s: str):
    """Parsea una fecha YYYY-MM-DD a datetime UTC."""
    if not s:
        return None
    try:
        d = datetime.datetime.strptime(s, "%Y-%m-%d")
        return d.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida: {s} (formato esperado YYYY-MM-DD)")


def _progress(label):
    def cb(n):
        print(f"\r{C.DIM}  [{label}] {n} registros procesados...{C.RESET}",
              end="", flush=True)
    return cb


def cmd_scan(args):
    print_banner()

    if not os.path.isfile(args.mft):
        print(f"{C.RED}[!] No existe el fichero MFT: {args.mft}{C.RESET}")
        return 1

    total = count_records(args.mft)
    print(f"{C.CYAN}[*] Fichero MFT: {args.mft}{C.RESET}")
    print(f"{C.CYAN}[*] Registros totales: {total}{C.RESET}")
    print(f"{C.CYAN}[*] Analizando...{C.RESET}")

    config = AnalysisConfig(
        system_install=args.system_install,
        include_directories=args.include_dirs,
        only_in_use=args.only_in_use,
        min_score=args.min_score,
        enable_h3=not args.no_h3,
    )

    records = parse_mft_file(args.mft, max_records=args.max_records,
                             progress_cb=_progress("MFT"))
    verdicts, stats = analyze_records(records, config)
    print()  # salto tras la barra de progreso

    # Corroboración con USN Journal
    corroborated = 0
    if args.usn:
        if os.path.isfile(args.usn):
            print(f"{C.CYAN}[*] Procesando USN Journal: {args.usn}{C.RESET}")
            creation_index = build_creation_index(
                args.usn, progress_cb=_progress("USN"))
            print()
            corroborated = corroborate(verdicts, creation_index)
            # Recalcular stats tras corroboración
            stats["files_flagged"] = len(verdicts)
            stats["critical"] = sum(
                1 for v in verdicts if v.suspicion_level == "CRÍTICO")
            stats["high"] = sum(
                1 for v in verdicts if v.suspicion_level == "ALTO")
            stats["medium"] = sum(
                1 for v in verdicts if v.suspicion_level == "MEDIO")
            stats["low"] = sum(
                1 for v in verdicts if v.suspicion_level == "BAJO")
            print(f"{C.GREEN}[+] {corroborated} archivo(s) corroborados "
                  f"con el USN Journal{C.RESET}")
        else:
            print(f"{C.YELLOW}[!] USN Journal no encontrado: {args.usn} "
                  f"(continuo sin corroboración){C.RESET}")

    # Informe de consola
    print_console_report(verdicts, stats, use_color=not args.no_color,
                         max_items=args.top)

    # Metadatos para los informes
    meta = {
        "mft_file": args.mft,
        "usn_journal": args.usn or "(no proporcionado)",
        "total_records": total,
        "corroborated_with_usn": corroborated,
        "system_install": str(args.system_install) if args.system_install
                          else "(no especificado)",
        "heimdall_timewatch_version": __version__,
    }

    # Exportaciones
    if args.json:
        export_json(verdicts, stats, args.json, meta)
        print(f"{C.GREEN}[+] JSON: {args.json}{C.RESET}")
    if args.csv:
        export_csv(verdicts, args.csv)
        print(f"{C.GREEN}[+] CSV: {args.csv}{C.RESET}")
    if args.html:
        export_html(verdicts, stats, args.html, meta)
        print(f"{C.GREEN}[+] HTML: {args.html}{C.RESET}")

    return 0


def cmd_lab(args):
    from .labgen import generate_lab_mft

    print_banner()
    print(f"{C.MAGENTA}[*] MODO LABORATORIO{C.RESET}")
    print(f"{C.DIM}    Genero un MFT sintético con casos de timestomping "
          f"plantados y lo analizo.{C.RESET}\n")

    workdir = args.output_dir or tempfile.mkdtemp(prefix="heimdall_lab_")
    os.makedirs(workdir, exist_ok=True)
    mft_path = os.path.join(workdir, "$MFT_lab")

    planted = generate_lab_mft(mft_path, n_clean=args.clean_files)

    print(f"{C.CYAN}[*] MFT de laboratorio: {mft_path}{C.RESET}")
    print(f"{C.CYAN}[*] Casos plantados ({len(planted)}):{C.RESET}")
    for rec_no, label in planted:
        print(f"    {C.YELLOW}MFT #{rec_no}{C.RESET} → {label}")
    print()

    # Analizar
    config = AnalysisConfig(min_score=1, enable_h3=True)
    records = parse_mft_file(mft_path)
    verdicts, stats = analyze_records(records, config)

    print_console_report(verdicts, stats, use_color=not args.no_color)

    # Verificación: ¿encontró el detector los casos plantados?
    print(f"{C.BOLD}═══ VERIFICACIÓN (¿detectamos lo plantado?) ═══{C.RESET}")
    flagged_records = {v.record_number for v in verdicts}
    hits = 0
    for rec_no, label in planted:
        if rec_no in flagged_records:
            print(f"  {C.GREEN}✓ DETECTADO{C.RESET}  MFT #{rec_no} — {label}")
            hits += 1
        else:
            print(f"  {C.RED}✗ NO detectado{C.RESET}  MFT #{rec_no} — {label}")
    print(f"\n  {C.BOLD}Detección: {hits}/{len(planted)} casos plantados"
          f"{C.RESET}\n")

    if args.html:
        meta = {"mode": "laboratorio", "mft_file": mft_path,
                "planted_cases": len(planted), "detected": hits}
        export_html(verdicts, stats, args.html, meta)
        print(f"{C.GREEN}[+] HTML: {args.html}{C.RESET}")

    return 0


def cmd_parse(args):
    """Vuelca los timestamps crudos a CSV sin aplicar detección."""
    import csv as _csv
    print_banner()
    print(f"{C.CYAN}[*] Volcando timestamps de {args.mft} a {args.output}"
          f"{C.RESET}")

    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow([
            "record", "filename", "is_dir", "in_use",
            "SI_created", "SI_modified", "SI_mftmod", "SI_accessed",
            "FN_created", "FN_modified", "FN_mftmod", "FN_accessed",
        ])
        n = 0
        for rec in parse_mft_file(args.mft, max_records=args.max_records):
            si = rec.si_timestamps
            fn = rec.fn_timestamps
            w.writerow([
                rec.record_number, rec.filename or "", rec.is_directory,
                rec.in_use,
                si.created if si else "", si.modified if si else "",
                si.mft_modified if si else "", si.accessed if si else "",
                fn.created if fn else "", fn.modified if fn else "",
                fn.mft_modified if fn else "", fn.accessed if fn else "",
            ])
            n += 1
    print(f"{C.GREEN}[+] {n} registros volcados a {args.output}{C.RESET}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="heimdall-timewatch",
        description="Detector de timestomping en NTFS ($SI vs $FN + USN). "
                    "Creado por Heindall para DFIR/Blue Team autorizado.",
        epilog="Recuerda: ningún indicador es prueba concluyente. Corrobora.",
    )
    p.add_argument("--version", action="version",
                   version=f"heimdall-timewatch {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # scan
    s = sub.add_parser("scan", help="Analizar un fichero $MFT real")
    s.add_argument("-m", "--mft", required=True, help="Ruta al fichero $MFT")
    s.add_argument("--usn", help="Ruta al $UsnJrnl:$J (corroboración)")
    s.add_argument("--system-install", type=_parse_date,
                   help="Fecha de instalación del SO (YYYY-MM-DD) para H5")
    s.add_argument("--min-score", type=int, default=1,
                   help="Umbral mínimo de score para reportar (def: 1)")
    s.add_argument("--top", type=int, default=None,
                   help="Mostrar solo los N más sospechosos en consola")
    s.add_argument("--max-records", type=int, default=None,
                   help="Limitar nº de registros (para pruebas)")
    s.add_argument("--include-dirs", action="store_true",
                   help="Incluir directorios en el análisis")
    s.add_argument("--only-in-use", action="store_true",
                   help="Analizar solo archivos en uso (no borrados)")
    s.add_argument("--no-h3", action="store_true",
                   help="Desactivar H3 (RID disorder, ruidoso)")
    s.add_argument("--json", help="Exportar hallazgos a JSON")
    s.add_argument("--csv", help="Exportar hallazgos a CSV")
    s.add_argument("--html", help="Exportar informe HTML")
    s.add_argument("--no-color", action="store_true",
                   help="Desactivar color en consola")
    s.set_defaults(func=cmd_scan)

    # lab
    l = sub.add_parser("lab", help="Generar y analizar un MFT de laboratorio")
    l.add_argument("--output-dir", help="Directorio para el MFT de lab")
    l.add_argument("--clean-files", type=int, default=200,
                   help="Nº de archivos limpios a generar (def: 200)")
    l.add_argument("--html", help="Exportar informe HTML del lab")
    l.add_argument("--no-color", action="store_true",
                   help="Desactivar color en consola")
    l.set_defaults(func=cmd_lab)

    # parse
    pa = sub.add_parser("parse", help="Volcar timestamps a CSV (sin juzgar)")
    pa.add_argument("-m", "--mft", required=True, help="Ruta al fichero $MFT")
    pa.add_argument("-o", "--output", required=True, help="CSV de salida")
    pa.add_argument("--max-records", type=int, default=None)
    pa.set_defaults(func=cmd_parse)

    return p


def _force_utf8_output():
    """Reconfigura stdout/stderr a UTF-8.

    En Windows la consola usa por defecto cp1252 y revienta al imprimir los
    caracteres del banner y de los informes (→, •, ═, ✓). Forzamos UTF-8 con
    reemplazo para que la herramienta corra sin configuración previa.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}[!] Interrumpido por el usuario{C.RESET}")
        return 130


if __name__ == "__main__":
    sys.exit(main())
