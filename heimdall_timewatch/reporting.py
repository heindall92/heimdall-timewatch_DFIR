"""
heimdall-timewatch :: reporting.py
═══════════════════════════════════════════════════════════════════════════

Generación de informes de los hallazgos en varios formatos:
  · Consola (con color ANSI)
  · JSON   (para integración con SIEM / pipelines)
  · CSV    (para abrir en Excel / Timeline Explorer)
  · HTML   (informe navegable y presentable)

Autor: Yoandy Ramirez Delgado  |  Uso educativo / DFIR autorizado
"""

from __future__ import annotations

import json
import csv
import html
import datetime
from typing import Optional


# ───────────────────────────────────────────────────────────────────────────
# Colores ANSI para consola
# ───────────────────────────────────────────────────────────────────────────

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GREY = "\033[90m"


LEVEL_COLOR = {
    "CRÍTICO": C.RED + C.BOLD,
    "ALTO": C.RED,
    "MEDIO": C.YELLOW,
    "BAJO": C.CYAN,
    "LIMPIO": C.GREEN,
}

CONF_COLOR = {
    "ALTA": C.RED + C.BOLD,
    "MEDIA": C.YELLOW,
    "BAJA": C.CYAN,
}


BANNER = r"""
   __ __    _         __     ____      __  _                       __      __
  / // /__ (_)_ _  ___/ /__ _/ / /____ / /_(_)_ _  ___ _    _____ _/ /_____/ /
 / _  / -_) /  ' \/ _  / _ `/ / /___// __/ /  ' \/ -_) |/|/ / _ `/ __/ __/ _ \
/_//_/\__/_/_/_/_/\_,_/\_,_/_/_/      \__/_/_/_/_/\__/|__,__/\_,_/\__/\__/_//_/

        TimeStomp Detector :: $SI vs $FN + USN Journal corroboration
                      "El guardián que ve el tiempo"
"""


def print_banner():
    print(C.CYAN + BANNER + C.RESET)


# ───────────────────────────────────────────────────────────────────────────
# Informe de consola
# ───────────────────────────────────────────────────────────────────────────

def print_console_report(verdicts, stats, use_color: bool = True,
                         max_items: Optional[int] = None):
    """Imprime el informe en consola."""
    def col(text, color):
        return f"{color}{text}{C.RESET}" if use_color else text

    print()
    print(col("═" * 75, C.BLUE))
    print(col("  RESUMEN DEL ANÁLISIS", C.BOLD))
    print(col("═" * 75, C.BLUE))
    print(f"  Registros vistos:        {stats['total_records_seen']}")
    print(f"  Archivos analizados:     {stats['files_analyzed']}")
    print(f"  Directorios omitidos:    {stats['skipped_directories']}")
    print(f"  {col('Archivos marcados:', C.BOLD)}       "
          f"{col(str(stats['files_flagged']), C.YELLOW)}")
    print()
    print(f"    {col('CRÍTICO', LEVEL_COLOR['CRÍTICO'])}: {stats['critical']}    "
          f"{col('ALTO', LEVEL_COLOR['ALTO'])}: {stats['high']}    "
          f"{col('MEDIO', LEVEL_COLOR['MEDIO'])}: {stats['medium']}    "
          f"{col('BAJO', LEVEL_COLOR['BAJO'])}: {stats['low']}")
    print(col("═" * 75, C.BLUE))
    print()

    if not verdicts:
        print(col("  ✓ No se detectaron indicadores de timestomping.", C.GREEN))
        print(col("    (Recuerda: ausencia de indicadores no es prueba de "
                  "ausencia de manipulación)", C.DIM))
        print()
        return

    items = verdicts[:max_items] if max_items else verdicts
    for i, v in enumerate(items, 1):
        level_c = LEVEL_COLOR.get(v.suspicion_level, "")
        name = v.filename or f"<sin nombre> (registro {v.record_number})"
        kind = "DIR" if v.is_directory else "archivo"
        status = "en uso" if v.in_use else "BORRADO"

        print(col(f"[{i}] ", C.BOLD) +
              col(f"{v.suspicion_level}", level_c) +
              col(f"  (score {v.score})", C.DIM))
        print(f"    {col('Nombre:', C.BOLD)}  {name}")
        print(f"    {col('MFT #:', C.DIM)}   {v.record_number}  "
              f"[{kind}, {status}]")
        print(f"    {col('Hallazgos:', C.BOLD)}")
        for f in v.findings:
            conf_c = CONF_COLOR.get(f.confidence, "")
            print(f"      • [{f.code}] {col(f.title, C.BOLD)} "
                  f"({col(f.confidence, conf_c)})")
            print(col(f"          {f.detail}", C.GREY))
        print()


# ───────────────────────────────────────────────────────────────────────────
# Exportadores
# ───────────────────────────────────────────────────────────────────────────

def _verdict_to_dict(v):
    return {
        "record_number": v.record_number,
        "filename": v.filename,
        "is_directory": v.is_directory,
        "in_use": v.in_use,
        "suspicion_level": v.suspicion_level,
        "score": v.score,
        "findings": [
            {
                "code": f.code,
                "title": f.title,
                "confidence": f.confidence,
                "detail": f.detail,
                "false_positive_note": f.false_positive_note,
            }
            for f in v.findings
        ],
    }


def export_json(verdicts, stats, path: str, meta: Optional[dict] = None):
    """Exporta a JSON (ideal para SIEM / pipelines)."""
    payload = {
        "tool": "heimdall-timewatch",
        "generated_utc": datetime.datetime.now(
            tz=datetime.timezone.utc
        ).isoformat(),
        "meta": meta or {},
        "stats": stats,
        "findings": [_verdict_to_dict(v) for v in verdicts],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


def export_csv(verdicts, path: str):
    """Exporta a CSV (una fila por hallazgo, para Excel/Timeline Explorer)."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "record_number", "filename", "is_directory", "in_use",
            "suspicion_level", "score", "finding_code", "finding_title",
            "confidence", "detail",
        ])
        for v in verdicts:
            if not v.findings:
                continue
            for f in v.findings:
                w.writerow([
                    v.record_number, v.filename or "", v.is_directory,
                    v.in_use, v.suspicion_level, v.score, f.code, f.title,
                    f.confidence, f.detail,
                ])


def export_html(verdicts, stats, path: str, meta: Optional[dict] = None):
    """Exporta a un informe HTML navegable y presentable."""
    meta = meta or {}
    rows = []
    for i, v in enumerate(verdicts, 1):
        findings_html = "".join(
            f"""
            <div class="finding conf-{f.confidence}">
              <span class="code">{html.escape(f.code)}</span>
              <span class="ftitle">{html.escape(f.title)}</span>
              <span class="conf">{html.escape(f.confidence)}</span>
              <div class="detail">{html.escape(f.detail)}</div>
              <div class="fp">⚠ Falsos positivos: {html.escape(f.false_positive_note)}</div>
            </div>
            """
            for f in v.findings
        )
        name = html.escape(v.filename or f"<sin nombre #{v.record_number}>")
        rows.append(f"""
        <div class="card level-{v.suspicion_level}">
          <div class="card-head">
            <span class="rank">#{i}</span>
            <span class="level">{v.suspicion_level}</span>
            <span class="score">score {v.score}</span>
          </div>
          <div class="fname">{name}</div>
          <div class="meta">MFT #{v.record_number} ·
            {"DIR" if v.is_directory else "archivo"} ·
            {"en uso" if v.in_use else "BORRADO"}</div>
          <div class="findings">{findings_html}</div>
        </div>
        """)

    generated = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    meta_html = "".join(
        f"<li><b>{html.escape(str(k))}:</b> {html.escape(str(v))}</li>"
        for k, v in meta.items()
    )

    doc = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>heimdall-timewatch :: Informe de Timestomping</title>
<style>
  :root {{
    --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#c9d1d9;
    --crit:#f85149; --high:#ff7b72; --med:#d29922; --low:#58a6ff; --ok:#3fb950;
    --mute:#8b949e;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font-family:"Segoe UI",system-ui,sans-serif; line-height:1.5; }}
  header {{ background:linear-gradient(135deg,#1f2937,#0d1117);
    padding:32px; border-bottom:2px solid var(--low); }}
  h1 {{ margin:0; font-size:24px; color:var(--low); }}
  .sub {{ color:var(--mute); margin-top:4px; font-size:13px; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
  .summary {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px;
    margin-bottom:24px; }}
  .stat {{ background:var(--panel); border:1px solid var(--border);
    border-radius:8px; padding:16px; text-align:center; }}
  .stat .n {{ font-size:28px; font-weight:700; }}
  .stat .l {{ color:var(--mute); font-size:12px; text-transform:uppercase; }}
  .crit .n {{ color:var(--crit); }} .high .n {{ color:var(--high); }}
  .med .n {{ color:var(--med); }} .low .n {{ color:var(--low); }}
  .meta-box {{ background:var(--panel); border:1px solid var(--border);
    border-radius:8px; padding:16px; margin-bottom:24px; }}
  .meta-box ul {{ margin:0; padding-left:18px; color:var(--mute);
    font-size:13px; }}
  .card {{ background:var(--panel); border:1px solid var(--border);
    border-left:4px solid var(--mute); border-radius:8px; padding:16px;
    margin-bottom:16px; }}
  .card.level-CRÍTICO {{ border-left-color:var(--crit); }}
  .card.level-ALTO {{ border-left-color:var(--high); }}
  .card.level-MEDIO {{ border-left-color:var(--med); }}
  .card.level-BAJO {{ border-left-color:var(--low); }}
  .card-head {{ display:flex; gap:12px; align-items:center;
    margin-bottom:8px; }}
  .rank {{ color:var(--mute); font-weight:700; }}
  .level {{ font-weight:700; padding:2px 10px; border-radius:12px;
    background:#21262d; font-size:12px; }}
  .level-CRÍTICO .level {{ color:var(--crit); }}
  .score {{ color:var(--mute); font-size:12px; }}
  .fname {{ font-size:16px; font-weight:600; word-break:break-all; }}
  .meta {{ color:var(--mute); font-size:12px; margin-bottom:12px; }}
  .finding {{ background:#0d1117; border:1px solid var(--border);
    border-radius:6px; padding:10px; margin-top:8px; }}
  .finding .code {{ font-weight:700; color:var(--low);
    margin-right:8px; }}
  .finding .ftitle {{ font-weight:600; }}
  .finding .conf {{ float:right; font-size:11px; padding:1px 8px;
    border-radius:10px; background:#21262d; }}
  .conf-ALTA {{ border-left:3px solid var(--crit); }}
  .conf-MEDIA {{ border-left:3px solid var(--med); }}
  .conf-BAJA {{ border-left:3px solid var(--low); }}
  .detail {{ color:var(--text); font-size:13px; margin-top:6px;
    font-family:"Cascadia Code",Consolas,monospace; }}
  .fp {{ color:var(--mute); font-size:12px; margin-top:6px;
    font-style:italic; }}
  .disclaimer {{ background:#21262d; border:1px solid var(--med);
    border-radius:8px; padding:16px; margin-bottom:24px; color:var(--med);
    font-size:13px; }}
  footer {{ text-align:center; color:var(--mute); padding:24px;
    font-size:12px; }}
</style></head><body>
<header>
  <h1>🛡️ heimdall-timewatch — Informe de Detección de Timestomping</h1>
  <div class="sub">$STANDARD_INFORMATION vs $FILE_NAME + corroboración USN Journal · generado {html.escape(generated)} UTC</div>
</header>
<div class="wrap">
  <div class="disclaimer">
    <b>Lectura DFIR responsable:</b> ningún indicador aquí mostrado es prueba
    concluyente por sí solo. Son señales que requieren corroboración y juicio
    del analista. Cada hallazgo incluye sus falsos positivos conocidos. La
    ausencia de indicadores no demuestra ausencia de manipulación.
  </div>
  <div class="meta-box"><ul>{meta_html}</ul></div>
  <div class="summary">
    <div class="stat crit"><div class="n">{stats['critical']}</div><div class="l">Crítico</div></div>
    <div class="stat high"><div class="n">{stats['high']}</div><div class="l">Alto</div></div>
    <div class="stat med"><div class="n">{stats['medium']}</div><div class="l">Medio</div></div>
    <div class="stat low"><div class="n">{stats['low']}</div><div class="l">Bajo</div></div>
    <div class="stat"><div class="n">{stats['files_analyzed']}</div><div class="l">Analizados</div></div>
  </div>
  {"".join(rows) if rows else '<div class="card"><div class="fname">✓ Sin indicadores de timestomping</div></div>'}
</div>
<footer>heimdall-timewatch · creado por Yoandy Ramirez Delgado · uso educativo / DFIR autorizado</footer>
</body></html>"""

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
