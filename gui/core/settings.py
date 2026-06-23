"""Persistencia de ajustes en JSON (%APPDATA%/HeimdallTimeWatch)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .secrets import get_cloud_api_key, set_cloud_api_key

DEFAULTS: dict[str, str] = {
    "ollama_model": "llama3.2",
    "ollama_host": "http://localhost:11434",
    "ollama_provider": "local",
    "ollama_cloud_host": "https://ollama.com",
    "ollama_cloud_model": "gpt-oss:120b",
    "min_score": "1",
    "include_directories": "false",
    "only_in_use": "false",
    "enable_h3": "true",
    "system_install": "",
    "last_mft": "",
    "last_usn": "",
    "theme": "dark",
    "locale": "es",
    "user_name": "Analista DFIR",
    "user_role": "Analista forense",
    "user_bio": "",
    "org_name": "",
    "user_department": "",
    "user_email": "",
    "user_phone": "",
    "user_location": "",
    "user_linkedin": "",
    "user_github": "",
    "user_twitter": "",
    "user_website": "",
    "user_avatar": "",
}

SETTING_KEYS = set(DEFAULTS)


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "HeimdallTimeWatch"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def _load_raw() -> dict[str, str]:
    path = settings_path()
    if not path.is_file():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in SETTING_KEYS:
                merged[key] = str(value)
    return merged


def get_all_settings() -> dict[str, str]:
    merged = _load_raw()
    merged["ollama_cloud_key"] = get_cloud_api_key()
    return merged


def save_settings(payload: dict[str, Any]) -> None:
    current = _load_raw()
    if "ollama_cloud_key" in payload:
        set_cloud_api_key(str(payload.pop("ollama_cloud_key") or ""))
    for key, value in payload.items():
        if key in SETTING_KEYS:
            current[key] = str(value)
    settings_path().write_text(
        json.dumps(current, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
