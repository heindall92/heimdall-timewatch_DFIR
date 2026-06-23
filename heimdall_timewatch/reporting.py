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
import re
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

def verdict_to_dict(v):
    return {
        "record_number": v.record_number,
        "filename": v.filename,
        "is_directory": v.is_directory,
        "in_use": v.in_use,
        "suspicion_level": v.suspicion_level,
        "score": v.score,
        "filename_namespace": v.filename_namespace,
        "parent_ref": v.parent_ref,
        "si_created": v.si_created,
        "si_modified": v.si_modified,
        "si_mft_modified": v.si_mft_modified,
        "si_accessed": v.si_accessed,
        "fn_created": v.fn_created,
        "fn_modified": v.fn_modified,
        "fn_mft_modified": v.fn_mft_modified,
        "fn_accessed": v.fn_accessed,
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
        "findings": [verdict_to_dict(v) for v in verdicts],
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
    --bg:#eef2ff; --bg2:#f8fafc; --panel:rgba(255,255,255,0.72);
    --border:rgba(100,116,139,0.34); --border-strong:rgba(100,116,139,0.48);
    --text:#0f172a; --text2:#334155; --mute:#64748b;
    --blue:#2563eb; --blue-soft:rgba(59,130,246,0.12);
    --crit:#ef4444; --high:#f97316; --med:#eab308; --low:#3b82f6;
    --radius:14px; --shadow:0 8px 28px rgba(15,23,42,0.07),0 2px 8px rgba(59,130,246,0.05);
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--text);
    font-family:"Segoe UI",Inter,system-ui,sans-serif; line-height:1.55;
    background:linear-gradient(145deg,var(--bg) 0%,var(--bg2) 42%,#e0e7ff 100%);
    min-height:100vh;
  }}
  header {{
    background:linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.58));
    backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
    padding:28px 32px; border-bottom:1px solid var(--border);
    box-shadow:var(--shadow);
  }}
  h1 {{ margin:0; font-size:24px; color:var(--blue); letter-spacing:-0.02em; }}
  .sub {{ color:var(--mute); margin-top:6px; font-size:13px; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
  .summary {{ display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px; }}
  .stat, .meta-box, .card, .disclaimer {{
    background:var(--panel);
    border:1px solid var(--border);
    border-radius:var(--radius);
    box-shadow:var(--shadow);
    backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
  }}
  .stat {{ padding:16px; text-align:center; }}
  .stat .n {{ font-size:28px; font-weight:700; font-family:"Cascadia Code",Consolas,monospace; }}
  .stat .l {{ color:var(--mute); font-size:11px; text-transform:uppercase; letter-spacing:0.06em; }}
  .crit .n {{ color:var(--crit); }} .high .n {{ color:var(--high); }}
  .med .n {{ color:var(--med); }} .low .n {{ color:var(--low); }}
  .meta-box {{ padding:16px 18px; margin-bottom:20px; }}
  .meta-box ul {{ margin:0; padding-left:18px; color:var(--text2); font-size:13px; }}
  .card {{
    border-left:4px solid var(--border-strong); padding:16px 18px; margin-bottom:14px;
  }}
  .card.level-CRÍTICO {{ border-left-color:var(--crit); }}
  .card.level-ALTO {{ border-left-color:var(--high); }}
  .card.level-MEDIO {{ border-left-color:var(--med); }}
  .card.level-BAJO {{ border-left-color:var(--low); }}
  .card-head {{ display:flex; gap:12px; align-items:center; margin-bottom:8px; flex-wrap:wrap; }}
  .rank {{ color:var(--mute); font-weight:700; }}
  .level {{
    font-weight:700; padding:3px 10px; border-radius:999px;
    background:var(--blue-soft); font-size:11px; color:var(--blue);
  }}
  .card.level-CRÍTICO .level {{ background:rgba(239,68,68,0.12); color:var(--crit); }}
  .card.level-ALTO .level {{ background:rgba(249,115,22,0.12); color:var(--high); }}
  .score {{ color:var(--mute); font-size:12px; }}
  .fname {{ font-size:16px; font-weight:600; word-break:break-all; color:var(--text); }}
  .meta {{ color:var(--mute); font-size:12px; margin-bottom:12px; }}
  .finding {{
    background:rgba(255,255,255,0.55); border:1px solid var(--border);
    border-radius:10px; padding:10px 12px; margin-top:8px;
  }}
  .finding .code {{ font-weight:700; color:var(--blue); margin-right:8px; }}
  .finding .ftitle {{ font-weight:600; color:var(--text); }}
  .finding .conf {{
    float:right; font-size:11px; padding:2px 8px; border-radius:999px;
    background:rgba(148,163,184,0.15); color:var(--text2);
  }}
  .conf-ALTA {{ border-left:3px solid var(--crit); }}
  .conf-MEDIA {{ border-left:3px solid var(--med); }}
  .conf-BAJA {{ border-left:3px solid var(--low); }}
  .detail {{ color:var(--text2); font-size:13px; margin-top:6px;
    font-family:"Cascadia Code",Consolas,monospace; }}
  .fp {{ color:var(--mute); font-size:12px; margin-top:6px; font-style:italic; }}
  .disclaimer {{
    border-color:rgba(234,179,8,0.45); background:rgba(255,251,235,0.72);
    padding:16px 18px; margin-bottom:20px; color:#92400e; font-size:13px;
  }}
  .license-note {{
    border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px;
    margin-bottom:20px; background:rgba(255,255,255,0.58); color:var(--text2); font-size:12px;
  }}
  footer {{
    text-align:center; color:var(--mute); padding:28px 16px 36px; font-size:12px;
    border-top:1px solid var(--border); margin-top:12px;
  }}
</style></head><body>
<header>
  <h1>🛡️ Heimdall Timewatch — Informe de detección de timestomping</h1>
  <div class="sub">$STANDARD_INFORMATION vs $FILE_NAME · corroboración USN Journal · generado {html.escape(generated)} UTC</div>
</header>
<div class="wrap">
  <div class="license-note">
    <b>Licencia MIT:</b> informe generado con Heimdall Timewatch, software libre.
    © {datetime.datetime.now().year} Yoandy Ramirez Delgado (Heindall). Eres libre de usar,
    modificar y redistribuir conservando el aviso de copyright.
  </div>
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
<footer>Heimdall Timewatch · Yoandy Ramirez Delgado (Heindall) · Licencia MIT · DFIR autorizado</footer>
</body></html>"""

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)


def _extract_ai_title(content: str, fallback: str = "Resumen IA") -> str:
    for line in content.splitlines():
        stripped = line.strip()
        m = re.match(r"^#{1,2}\s+(.+)$", stripped)
        if m:
            title = re.sub(r"\*+", "", m.group(1)).strip()
            if title:
                return title[:120]
    return fallback


def _ai_inline(text: str) -> str:
    """Formato inline: código, negrita, cursiva y badges DFIR."""
    escaped = html.escape(text)
    escaped = re.sub(
        r"`([^`]+)`",
        r'<code class="inline-code">\1</code>',
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(
        r"\bH([1-6])-H([1-6])\b",
        r'<span class="badge badge-heur">H\1-H\2</span>',
        escaped,
    )
    escaped = re.sub(
        r"\b(H[1-6])\b",
        r'<span class="badge badge-heur">\1</span>',
        escaped,
    )
    escaped = re.sub(
        r"(\b(?:[A-Za-z]:\\|\\\\)[^\s<>&quot;']+)",
        r'<span class="path">\1</span>',
        escaped,
    )
    escaped = re.sub(
        r"(\b[\w\-]+\.(?:exe|dll|sys|dat|bin|ps1|bat|cmd|vbs|js|jar|msi|lnk|pf|evtx|log|mft)\b)",
        r'<span class="artifact">\1</span>',
        escaped,
        flags=re.IGNORECASE,
    )
    for level, cls in (
        ("CRÍTICO", "crit"),
        ("CRITICO", "crit"),
        ("CRITICAL", "crit"),
        ("ALTO", "high"),
        ("HIGH", "high"),
        ("MEDIO", "med"),
        ("MEDIUM", "med"),
        ("BAJO", "low"),
        ("LOW", "low"),
    ):
        escaped = re.sub(
            rf"\b{re.escape(level)}\b",
            rf'<span class="badge badge-{cls}">{level}</span>',
            escaped,
        )
    return escaped


def _is_table_separator(line: str) -> bool:
    s = line.strip()
    if "|" not in s:
        return False
    return bool(re.match(r"^[\|\s:\-]+$", s))


def _split_table_row(line: str) -> list[str]:
    row = line.strip().strip("|")
    return [cell.strip() for cell in row.split("|")]


def _render_ai_table(header: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_ai_inline(c)}</th>" for c in header)
    body = ""
    for row in rows:
        cells = row + [""] * (len(header) - len(row))
        body += "<tr>" + "".join(f"<td>{_ai_inline(c)}</td>" for c in cells[: len(header)]) + "</tr>"
    return f'<div class="table-wrap"><table class="data-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _render_ai_markdown(content: str) -> str:
    """Convierte markdown típico de Ollama a HTML semántico con estilo."""
    lines = content.strip().splitlines()
    out: list[str] = []
    i = 0
    in_code = False
    code_buf: list[str] = []
    list_buf: list[str] = []
    list_type = "ul"

    def flush_list() -> None:
        nonlocal list_buf, list_type
        if not list_buf:
            return
        tag = list_type
        items = "".join(f"<li>{_ai_inline(item)}</li>" for item in list_buf)
        out.append(f"<{tag} class='prose-list'>{items}</{tag}>")
        list_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_list()
            if in_code:
                code_text = html.escape("\n".join(code_buf))
                out.append(f'<pre class="code-block"><code>{code_text}</code></pre>')
                code_buf = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if not stripped:
            flush_list()
            i += 1
            continue

        if re.match(r"^#{1,4}\s+", stripped):
            flush_list()
            level = len(stripped) - len(stripped.lstrip("#"))
            level = min(max(level, 1), 4)
            title = stripped[level:].strip()
            out.append(f"<h{level} class='section-h{level}'>{_ai_inline(title)}</h{level}>")
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            flush_list()
            out.append("<hr class='divider' />")
            i += 1
            continue

        if "|" in stripped and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
            flush_list()
            header = _split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i]:
                if not lines[i].strip():
                    break
                rows.append(_split_table_row(lines[i]))
                i += 1
            out.append(_render_ai_table(header, rows))
            continue

        if re.match(r"^[-*•]\s+", stripped):
            flush_list()
            list_type = "ul"
            list_buf.append(re.sub(r"^[-*•]\s+", "", stripped))
            i += 1
            while i < len(lines) and re.match(r"^[-*•]\s+", lines[i].strip()):
                list_buf.append(re.sub(r"^[-*•]\s+", "", lines[i].strip()))
                i += 1
            flush_list()
            continue

        if re.match(r"^\d+\.\s+", stripped):
            flush_list()
            list_type = "ol"
            list_buf.append(re.sub(r"^\d+\.\s+", "", stripped))
            i += 1
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                list_buf.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            flush_list()
            continue

        if stripped.startswith(">"):
            flush_list()
            quote_lines = [stripped.lstrip(">").strip()]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            quote_html = "<br>".join(_ai_inline(q) for q in quote_lines)
            out.append(f'<blockquote class="callout">{quote_html}</blockquote>')
            continue

        flush_list()
        para_lines = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith("#")
                or nxt.startswith("```")
                or nxt.startswith(">")
                or re.match(r"^[-*•]\s+", nxt)
                or re.match(r"^\d+\.\s+", nxt)
                or ("|" in nxt and i + 1 < len(lines) and _is_table_separator(lines[i + 1]))
            ):
                break
            para_lines.append(nxt)
            i += 1
        joined = " ".join(para_lines)
        insight = re.match(
            r"^\*\*(Conclusi[oó]n|Recomendaci[oó]n|Resumen|Prioridad|Acci[oó]n|Hallazgo[s]?|Siguiente paso[s]?)\s*:?\*\*\s*(.*)$",
            joined,
            re.IGNORECASE,
        )
        if insight:
            label = insight.group(1).strip()
            body = insight.group(2).strip()
            out.append(
                f"<div class='insight'><span class='insight-label'>{html.escape(label)}</span>"
                f"<p class='insight-body'>{_ai_inline(body) if body else ''}</p></div>"
            )
        else:
            out.append(f"<p class='prose-p'>{_ai_inline(joined)}</p>")

    if in_code and code_buf:
        code_text = html.escape("\n".join(code_buf))
        out.append(f'<pre class="code-block"><code>{code_text}</code></pre>')
    flush_list()
    return "\n".join(out)


def _ai_toc(sections: list[str]) -> str:
    if len(sections) < 2:
        return ""
    items = "".join(
        f"<li><a href='#{html.escape(sid)}'>{html.escape(label)}</a></li>"
        for sid, label in sections
    )
    return f"<nav class='toc card'><div class='toc-title'>Contenido</div><ol>{items}</ol></nav>"


def _slugify_heading(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return slug.strip("-")[:48] or "section"


def export_ai_html(content: str, path: str, meta: Optional[dict] = None, title: str = "Resumen IA"):
    """Exporta un resumen generado por el asistente IA a HTML con plantilla Heimdall."""
    meta = meta or {}
    generated = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    year = datetime.datetime.now().year
    title = _extract_ai_title(content, fallback=title)

    meta_labels = {
        "mft_file": "Archivo MFT",
        "model": "Modelo IA",
        "scan_path": "Origen del escaneo",
        "generated_utc": "Generado",
    }
    meta_items = []
    for key, val in meta.items():
        if val in (None, ""):
            continue
        label = meta_labels.get(str(key), str(key).replace("_", " ").title())
        meta_items.append(
            f"<li><span class='meta-k'>{html.escape(label)}</span>"
            f"<span class='meta-v'>{html.escape(str(val))}</span></li>"
        )
    meta_html = "".join(meta_items)

    body_html = _render_ai_markdown(content)
    word_count = len(content.split())
    sections: list[tuple[str, str]] = []
    slug_counts: dict[str, int] = {}

    def _unique_slug(label: str) -> str:
        base = _slugify_heading(label)
        n = slug_counts.get(base, 0)
        slug_counts[base] = n + 1
        return base if n == 0 else f"{base}-{n + 1}"

    for m in re.finditer(
        r"<h([23]) class='section-h\1'>(.*?)</h\1>",
        body_html,
        flags=re.DOTALL,
    ):
        raw = re.sub(r"<[^>]+>", "", m.group(2))
        sections.append((_unique_slug(raw), raw))

    toc_html = _ai_toc(sections)
    if sections:
        idx = 0
        def _inject_id(match: re.Match) -> str:
            nonlocal idx
            if idx >= len(sections):
                return match.group(0)
            sid = sections[idx][0]
            idx += 1
            level = match.group(1)
            return f"<h{level} id='{sid}' class='section-h{level}'>"
        body_html = re.sub(
            r"<h([23]) class='section-h\1'>",
            _inject_id,
            body_html,
        )

    doc = f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>heimdall-timewatch :: {html.escape(title)}</title>
<style>
  :root {{
    --bg:#eef2ff; --bg2:#f8fafc; --panel:rgba(255,255,255,0.78);
    --panel-strong:rgba(255,255,255,0.92);
    --border:rgba(100,116,139,0.28); --border-strong:rgba(100,116,139,0.42);
    --text:#0f172a; --text2:#334155; --mute:#64748b;
    --blue:#2563eb; --blue-soft:rgba(59,130,246,0.12);
    --crit:#ef4444; --high:#f97316; --med:#eab308; --low:#3b82f6;
    --violet:#7c3aed;
    --radius:16px; --radius-sm:10px;
    --shadow:0 10px 32px rgba(15,23,42,0.08),0 2px 8px rgba(59,130,246,0.06);
    --font: "Segoe UI", Inter, system-ui, sans-serif;
    --mono: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--text); font-family:var(--font); line-height:1.65;
    background:linear-gradient(145deg,var(--bg) 0%,var(--bg2) 40%,#e0e7ff 100%);
    min-height:100vh;
  }}
  .hero {{
    background:linear-gradient(135deg,rgba(255,255,255,0.88),rgba(255,255,255,0.62));
    backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
    border-bottom:1px solid var(--border);
    box-shadow:var(--shadow);
    padding:32px 24px 28px;
  }}
  .hero-inner {{ max-width:920px; margin:0 auto; }}
  .hero-badge {{
    display:inline-flex; align-items:center; gap:8px;
    font-size:11px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase;
    color:var(--blue); background:var(--blue-soft);
    padding:6px 12px; border-radius:999px; margin-bottom:14px;
  }}
  .hero h1 {{
    margin:0 0 8px; font-size:clamp(1.35rem,3vw,1.85rem);
    letter-spacing:-0.03em; color:var(--text); line-height:1.25;
  }}
  .hero-sub {{ color:var(--mute); font-size:14px; margin:0; }}
  .hero-meta {{
    display:flex; flex-wrap:wrap; gap:16px; margin-top:18px;
    font-size:12px; color:var(--text2);
  }}
  .hero-meta span {{ display:inline-flex; align-items:center; gap:6px; }}
  .wrap {{ max-width:920px; margin:0 auto; padding:28px 20px 40px; }}
  .card {{
    background:var(--panel); border:1px solid var(--border); border-radius:var(--radius);
    box-shadow:var(--shadow); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
    margin-bottom:18px; overflow:hidden;
  }}
  .disclaimer {{
    border-color:rgba(234,179,8,0.45); background:rgba(255,251,235,0.82);
    padding:16px 20px; color:#92400e; font-size:13px; line-height:1.55;
  }}
  .disclaimer strong {{ color:#78350f; }}
  .meta-box {{ padding:16px 20px; }}
  .meta-box ul {{
    list-style:none; margin:0; padding:0;
    display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px 16px;
  }}
  .meta-box li {{
    display:flex; flex-direction:column; gap:2px;
    padding:10px 12px; background:rgba(255,255,255,0.55);
    border:1px solid var(--border); border-radius:var(--radius-sm);
  }}
  .meta-k {{ font-size:10px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:var(--mute); }}
  .meta-v {{ font-size:13px; color:var(--text2); word-break:break-word; font-family:var(--mono); }}
  .prose {{
    padding:28px 32px 32px; color:var(--text2); font-size:15px;
  }}
  .section-h1 {{
    font-size:1.45rem; color:var(--text); margin:28px 0 14px;
    padding-bottom:10px; border-bottom:2px solid var(--blue-soft);
    letter-spacing:-0.02em;
  }}
  .section-h1:first-child {{ margin-top:0; }}
  .section-h2 {{
    font-size:1.2rem; color:var(--text); margin:26px 0 12px;
    padding-left:12px; border-left:4px solid var(--blue);
  }}
  .section-h3 {{ font-size:1.05rem; color:var(--text); margin:20px 0 10px; }}
  .section-h4 {{ font-size:0.95rem; color:var(--mute); margin:16px 0 8px; text-transform:uppercase; letter-spacing:0.04em; }}
  .prose-p {{ margin:0 0 14px; }}
  .prose-list {{ margin:0 0 16px 0; padding-left:22px; }}
  .prose-list li {{ margin-bottom:8px; }}
  .divider {{ border:none; border-top:1px solid var(--border); margin:24px 0; }}
  .callout {{
    margin:16px 0; padding:14px 18px;
    border-left:4px solid var(--violet);
    background:rgba(124,58,237,0.06);
    border-radius:0 var(--radius-sm) var(--radius-sm) 0;
    color:var(--text2); font-size:14px;
  }}
  .code-block {{
    margin:16px 0; padding:16px 18px;
    background:#0f172a; color:#e2e8f0;
    border-radius:var(--radius-sm);
    font-family:var(--mono); font-size:13px; line-height:1.55;
    overflow-x:auto; white-space:pre-wrap; word-break:break-word;
  }}
  .inline-code {{
    font-family:var(--mono); font-size:0.88em;
    background:rgba(15,23,42,0.06); padding:2px 6px; border-radius:6px;
    color:#1e40af;
  }}
  .table-wrap {{
    margin:18px 0; overflow-x:auto;
    border:1px solid var(--border); border-radius:var(--radius-sm);
    background:var(--panel-strong);
  }}
  .data-table {{
    width:100%; border-collapse:collapse; font-size:13px;
  }}
  .data-table th {{
    text-align:left; padding:12px 14px;
    background:linear-gradient(180deg,rgba(59,130,246,0.1),rgba(59,130,246,0.04));
    color:var(--text); font-weight:700; font-size:11px;
    letter-spacing:0.04em; text-transform:uppercase;
    border-bottom:1px solid var(--border-strong);
  }}
  .data-table td {{
    padding:11px 14px; border-bottom:1px solid var(--border);
    vertical-align:top; color:var(--text2);
  }}
  .data-table tr:last-child td {{ border-bottom:none; }}
  .data-table tbody tr:hover td {{ background:rgba(59,130,246,0.04); }}
  .badge {{
    display:inline-block; font-size:11px; font-weight:700;
    padding:2px 8px; border-radius:999px; margin:0 2px;
    letter-spacing:0.02em;
  }}
  .badge-heur {{ background:rgba(124,58,237,0.12); color:var(--violet); }}
  .badge-crit {{ background:rgba(239,68,68,0.12); color:var(--crit); }}
  .badge-high {{ background:rgba(249,115,22,0.12); color:var(--high); }}
  .badge-med {{ background:rgba(234,179,8,0.15); color:#a16207; }}
  .badge-low {{ background:rgba(59,130,246,0.12); color:var(--low); }}
  .path {{
    font-family:var(--mono); font-size:0.9em;
    color:#1d4ed8; background:rgba(59,130,246,0.08);
    padding:1px 5px; border-radius:5px; word-break:break-all;
  }}
  .artifact {{
    font-family:var(--mono); font-size:0.9em; font-weight:600;
    color:#7c2d12; background:rgba(249,115,22,0.1);
    padding:1px 6px; border-radius:5px;
  }}
  .insight {{
    margin:18px 0; padding:16px 18px 14px;
    border:1px solid rgba(59,130,246,0.25);
    border-left:4px solid var(--blue);
    border-radius:0 var(--radius-sm) var(--radius-sm) 0;
    background:linear-gradient(90deg,rgba(59,130,246,0.08),rgba(255,255,255,0.4));
  }}
  .insight-label {{
    display:block; font-size:11px; font-weight:800;
    letter-spacing:0.07em; text-transform:uppercase;
    color:var(--blue); margin-bottom:6px;
  }}
  .insight-body {{ margin:0; color:var(--text); font-size:15px; }}
  .toc {{ padding:18px 22px; margin-bottom:18px; }}
  .toc-title {{
    font-size:11px; font-weight:800; letter-spacing:0.08em;
    text-transform:uppercase; color:var(--mute); margin-bottom:10px;
  }}
  .toc ol {{ margin:0; padding-left:20px; color:var(--text2); font-size:14px; }}
  .toc li {{ margin-bottom:6px; }}
  .toc a {{ color:var(--blue); text-decoration:none; }}
  .toc a:hover {{ text-decoration:underline; }}
  .license-note {{
    border:1px solid var(--border); border-radius:var(--radius-sm);
    padding:14px 16px; margin-top:8px;
    background:rgba(255,255,255,0.55); color:var(--mute); font-size:12px;
  }}
  footer {{
    text-align:center; color:var(--mute); padding:24px 16px 36px;
    font-size:12px; border-top:1px solid var(--border);
  }}
  @media print {{
    body {{ background:#fff; }}
    .hero, .card {{ box-shadow:none; backdrop-filter:none; }}
    .table-wrap {{ break-inside:avoid; }}
  }}
</style></head><body>
<header class="hero">
  <div class="hero-inner">
    <div class="hero-badge">🤖 Asistente IA · Ollama</div>
    <h1>{html.escape(title)}</h1>
    <p class="hero-sub">Informe generado por Heimdall Timewatch — análisis asistido para revisión DFIR</p>
    <div class="hero-meta">
      <span>📅 {html.escape(generated)}</span>
      <span>📝 ~{word_count} palabras</span>
      <span>🛡️ Heimdall Timewatch</span>
    </div>
  </div>
</header>
<div class="wrap">
  <div class="card disclaimer">
    <strong>Lectura DFIR responsable:</strong> las sugerencias de la IA no sustituyen el juicio del analista.
    Corrobore con evidencia primaria ($MFT, USN, logs) antes de conclusiones operativas o informes periciales.
  </div>
  {f'<div class="card meta-box"><ul>{meta_html}</ul></div>' if meta_html else ''}
  {toc_html}
  <article class="card prose">
    {body_html}
  </article>
  <div class="license-note">
    <strong>Licencia MIT:</strong> informe generado con Heimdall Timewatch (software libre) · © {year} Yoandy Ramirez Delgado (Heindall).
    Libre uso, modificación y redistribución conservando el aviso de copyright.
  </div>
</div>
<footer>Heimdall Timewatch · Yoandy Ramirez Delgado (Heindall) · Licencia MIT · DFIR autorizado</footer>
</body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
