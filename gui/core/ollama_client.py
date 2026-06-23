"""Cliente Ollama (local + cloud) para asistencia DFIR."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from .settings import get_all_settings

CLOUD_HOST = "https://ollama.com"
CLOUD_MODELS_FALLBACK = [
    "gpt-oss:120b",
    "gpt-oss:20b",
    "glm-5.1",
    "qwen3.5",
    "deepseek-v4-flash",
]
LOCAL_MODELS_SUGGESTED = ["llama3.2", "llama3.1:8b", "mistral:7b", "qwen2.5:7b"]

DFIR_SYSTEM_PROMPT = """Eres un asistente DFIR especializado en análisis de timestamps NTFS.
Trabajas con heimdall-timewatch, que compara $STANDARD_INFORMATION vs $FILE_NAME.

Reglas:
- Nunca afirmes timestomping como hecho probado; habla de indicadores y corroboración.
- Cita códigos de heurística (H1–H6) cuando aplique.
- Menciona falsos positivos conocidos.
- Responde en español, claro y conciso, orientado al analista forense.
"""


def _cloud_host(settings: dict[str, str]) -> str:
    raw = (settings.get("ollama_cloud_host") or CLOUD_HOST).strip().rstrip("/")
    if raw.endswith("/api"):
        raw = raw[:-4]
    return raw or CLOUD_HOST


def _host(settings: dict[str, str]) -> str:
    return settings.get("ollama_host", "http://localhost:11434").rstrip("/")


def _cloud_api(path: str, settings: dict[str, str]) -> str:
    base = _cloud_host(settings)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}/api{path}"


def _provider(settings: dict[str, str]) -> str:
    return settings.get("ollama_provider", "local").strip().lower() or "local"


def _resolved_model(settings: dict[str, str]) -> str:
    if _provider(settings) == "cloud":
        return (
            settings.get("ollama_cloud_model")
            or settings.get("ollama_model")
            or CLOUD_MODELS_FALLBACK[0]
        )
    return settings.get("ollama_model", "llama3.2")


def _pick_model(settings: dict[str, str], available: list[str]) -> str:
    preferred = _resolved_model(settings)
    if not available:
        return preferred
    if preferred in available:
        return preferred
    pref_base = preferred.split(":")[0]
    for name in available:
        if name.startswith(f"{pref_base}:"):
            return name
    return available[0]


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict:
    data = None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=ctx) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def _parse_model_names(data: dict) -> list[str]:
    models = data.get("models") or []
    names: list[str] = []
    for item in models:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return names


def test_connection(settings: dict[str, str] | None = None) -> dict[str, Any]:
    settings = settings or get_all_settings()
    provider = _provider(settings)
    model = _resolved_model(settings)

    if provider == "cloud":
        api_key = (settings.get("ollama_cloud_key") or "").strip()
        if not api_key:
            return {
                "ok": False,
                "connected": False,
                "provider": "cloud",
                "error": "API Key de Ollama Cloud no configurada",
                "model": model,
                "available_models": CLOUD_MODELS_FALLBACK,
            }
        try:
            data = _http_json(
                _cloud_api("/tags", settings),
                headers={"Authorization": f"Bearer {api_key}"},
            )
            models = _parse_model_names(data) or CLOUD_MODELS_FALLBACK
            return {
                "ok": True,
                "connected": True,
                "provider": "cloud",
                "model": _pick_model(settings, models),
                "available_models": models,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return {
                "ok": False,
                "connected": False,
                "provider": "cloud",
                "error": str(exc),
                "model": model,
                "available_models": CLOUD_MODELS_FALLBACK,
            }

    host = _host(settings)
    try:
        data = _http_json(f"{host}/api/tags")
        models = _parse_model_names(data)
        return {
            "ok": bool(models),
            "connected": bool(models),
            "provider": "local",
            "model": _pick_model(settings, models) if models else model,
            "available_models": models or LOCAL_MODELS_SUGGESTED,
            "host": host,
            "hint": None if models else "Ejecuta: ollama pull llama3.2",
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "connected": False,
            "provider": "local",
            "error": f"No se puede conectar con Ollama en {host}: {exc}",
            "model": model,
            "available_models": LOCAL_MODELS_SUGGESTED,
            "host": host,
        }


def check_status(settings: dict[str, str] | None = None) -> dict[str, Any]:
    result = test_connection(settings)
    return {
        "connected": result.get("connected", False),
        "model": result.get("model", _resolved_model(settings or {})),
        "available_models": result.get("available_models", []),
        "provider": result.get("provider", "local"),
        "error": result.get("error"),
        "hint": result.get("hint"),
    }


def list_models(settings: dict[str, str] | None = None) -> dict[str, Any]:
    status = test_connection(settings)
    return {
        "ok": status.get("connected", False),
        "models": status.get("available_models", []),
        "provider": status.get("provider"),
        "error": status.get("error"),
    }


def _chat_request(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    headers: dict[str, str] | None = None,
    timeout: int = 180,
) -> dict[str, Any]:
    payload = {"model": model, "messages": messages, "stream": False}
    data = _http_json(url, method="POST", payload=payload, headers=headers, timeout=timeout)
    content = data.get("message", {}).get("content", "")
    if not content and data.get("error"):
        return {"ok": False, "error": str(data["error"]), "content": ""}
    return {"ok": True, "content": content, "model": model}


def _run_chat(messages: list[dict[str, str]], settings: dict[str, str]) -> dict[str, Any]:
    status = test_connection(settings)
    if not status.get("connected"):
        err = status.get("error") or status.get("hint") or "Ollama no está disponible"
        return {"ok": False, "error": err, "content": ""}

    model = status.get("model") or _pick_model(settings, status.get("available_models") or [])
    full_messages = [{"role": "system", "content": DFIR_SYSTEM_PROMPT}] + messages

    try:
        if _provider(settings) == "cloud":
            api_key = (settings.get("ollama_cloud_key") or "").strip()
            return _chat_request(
                _cloud_api("/chat", settings),
                model,
                full_messages,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return _chat_request(f"{_host(settings)}/api/chat", model, full_messages)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": str(exc), "content": ""}


def chat_message(message: str, settings: dict[str, str] | None = None) -> dict[str, Any]:
    settings = settings or get_all_settings()
    text = (message or "").strip()
    if not text:
        return {"ok": False, "error": "Mensaje vacío", "content": ""}
    return _run_chat([{"role": "user", "content": text}], settings)


def analyze_findings(scan_payload: dict[str, Any], settings: dict[str, str] | None = None) -> dict[str, Any]:
    """Genera un resumen ejecutivo DFIR de los hallazgos actuales."""
    settings = settings or get_all_settings()
    stats = scan_payload.get("stats") or {}
    findings = scan_payload.get("findings") or []
    meta = scan_payload.get("meta") or {}

    top = findings[:12]
    lines = [
        f"MFT: {meta.get('mft_file', '?')}",
        f"USN: {meta.get('usn_journal', '?')}",
        f"Crítico: {stats.get('critical', 0)}, Alto: {stats.get('high', 0)}, "
        f"Medio: {stats.get('medium', 0)}, Bajo: {stats.get('low', 0)}",
        f"Archivos marcados: {stats.get('files_flagged', 0)}",
        "",
        "Top hallazgos:",
    ]
    for item in top:
        name = item.get("filename") or f"registro #{item.get('record_number')}"
        codes = ", ".join(f["code"] for f in item.get("findings", []))
        lines.append(
            f"- [{item.get('suspicion_level')}] score {item.get('score')} | "
            f"{name} | heurísticas: {codes or '—'}"
        )

    prompt = (
        "Analiza estos resultados de heimdall-timewatch y entrega:\n"
        "1) Resumen ejecutivo (3–5 frases)\n"
        "2) Prioridades de investigación (lista numerada)\n"
        "3) Qué corroborar con otras fuentes (USN, eventos, MFT raw, etc.)\n\n"
        + "\n".join(lines)
    )
    return _run_chat([{"role": "user", "content": prompt}], settings)
