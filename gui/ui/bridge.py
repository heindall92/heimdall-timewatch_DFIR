"""QWebChannel bridge — motor DFIR + Ollama."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QCoreApplication, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from gui.core.ollama_client import (
    analyze_findings,
    chat_message,
    check_status,
    list_models,
    test_connection,
)
from gui.core.settings import get_all_settings, save_settings
from gui.core.user_avatar import avatar_data_url, remove_avatar, save_avatar_data_url
from gui.core.workers import BackgroundWorker
from heimdall_timewatch.reporting import export_csv, export_html, export_json, export_ai_html
from heimdall_timewatch.scan_service import run_lab, run_scan


class Bridge(QObject):
    taskFinished = Signal(str)
    scanProgress = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._last_scan: dict | None = None

    def _emit_progress(self, phase: str, count: int) -> None:
        self.scanProgress.emit(json.dumps({"phase": phase, "count": count}))

    def _start_task(self, kind: str, task) -> str:
        request_id = uuid.uuid4().hex
        worker = BackgroundWorker(request_id, kind, task, self.taskFinished.emit)
        self._pool.start(worker)
        return json.dumps({"ok": True, "pending": True, "request_id": request_id})

    @Slot(result=str)
    def get_settings(self) -> str:
        try:
            data = get_all_settings()
            data["ollama_cloud_key"] = "********" if data.get("ollama_cloud_key") else ""
            data["user_avatar_url"] = avatar_data_url()
            return json.dumps({"ok": True, "settings": data}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(str, result=str)
    def save_user_avatar(self, data_url: str) -> str:
        try:
            result = save_avatar_data_url(data_url)
            save_settings({"user_avatar": "profile.jpg"})
            return json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @Slot(result=str)
    def remove_user_avatar(self) -> str:
        try:
            remove_avatar()
            save_settings({"user_avatar": ""})
            return json.dumps({"ok": True}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @Slot(str, result=str)
    def save_app_settings(self, payload: str) -> str:
        try:
            data = json.loads(payload) if payload else {}
            if isinstance(data, dict) and data.get("ollama_cloud_key") == "********":
                data.pop("ollama_cloud_key", None)
            save_settings(data)
            return json.dumps({"ok": True}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(result=str)
    def get_ollama_status(self) -> str:
        try:
            return json.dumps({"ok": True, **check_status(get_all_settings())}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @Slot(result=str)
    def test_ollama_connection(self) -> str:
        try:
            return json.dumps(test_connection(get_all_settings()), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @Slot(result=str)
    def get_ollama_models(self) -> str:
        try:
            return json.dumps(list_models(get_all_settings()), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc), "models": []})

    @Slot(str, result=str)
    def validate_path(self, path: str) -> str:
        """Comprueba si la ruta es un fichero válido (p. ej. $MFT)."""
        raw = (path or "").strip()
        if not raw:
            return json.dumps({"ok": False, "reason": "empty"})
        candidate = Path(raw)
        if candidate.is_dir():
            return json.dumps({"ok": False, "reason": "directory"})
        if not candidate.is_file():
            return json.dumps({"ok": False, "reason": "missing"})
        return json.dumps({"ok": True, "path": str(candidate.resolve())})

    @Slot(result=str)
    def quit_application(self) -> str:
        """Cierra la aplicación de escritorio."""
        app = QCoreApplication.instance()
        if app is not None:
            app.quit()
        return json.dumps({"ok": True})

    @Slot(str, result=str)
    def pick_file(self, kind: str) -> str:
        parent = self.parent()
        if kind == "mft":
            path, _ = QFileDialog.getOpenFileName(
                parent, "Seleccionar $MFT", "", "MFT ($MFT);;Todos (*.*)"
            )
        elif kind == "usn":
            path, _ = QFileDialog.getOpenFileName(
                parent, "Seleccionar $UsnJrnl:$J", "", "USN Journal (*);;Todos (*.*)"
            )
        elif kind == "json":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar JSON", "heimdall-informe.json", "JSON (*.json)"
            )
        elif kind == "csv":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar CSV", "heimdall-hallazgos.csv", "CSV (*.csv)"
            )
        elif kind == "html":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar HTML", "heimdall-informe.html", "HTML (*.html)"
            )
        else:
            path = ""
        return json.dumps({"ok": bool(path), "path": path or ""})

    @Slot(str, result=str)
    def start_scan(self, config_json: str) -> str:
        try:
            cfg = json.loads(config_json) if config_json else {}
            if not isinstance(cfg, dict):
                raise ValueError("Configuración inválida")

            mft = (cfg.get("mft") or "").strip()
            if not mft:
                return json.dumps({"ok": False, "error": "Selecciona un fichero $MFT"})

            def task():
                result = run_scan(
                    mft,
                    usn_path=(cfg.get("usn") or "").strip() or None,
                    system_install=(cfg.get("system_install") or "").strip() or None,
                    min_score=int(cfg.get("min_score") or 1),
                    max_records=int(cfg["max_records"]) if cfg.get("max_records") else None,
                    include_directories=bool(cfg.get("include_directories")),
                    only_in_use=bool(cfg.get("only_in_use")),
                    enable_h3=cfg.get("enable_h3", True) is not False,
                    progress_cb=self._emit_progress,
                )
                self._last_scan = {
                    "stats": result["stats"],
                    "meta": result["meta"],
                    "findings": result["findings"],
                    "planted": result.get("planted"),
                    "lab_hits": result.get("lab_hits"),
                    "lab_total": result.get("lab_total"),
                }
                save_settings(
                    {
                        "last_mft": mft,
                        "last_usn": (cfg.get("usn") or "").strip(),
                        "system_install": (cfg.get("system_install") or "").strip(),
                        "min_score": str(cfg.get("min_score") or 1),
                        "include_directories": str(bool(cfg.get("include_directories"))).lower(),
                        "only_in_use": str(bool(cfg.get("only_in_use"))).lower(),
                        "enable_h3": str(cfg.get("enable_h3", True) is not False).lower(),
                    }
                )
                return {
                    "ok": True,
                    "stats": result["stats"],
                    "meta": result["meta"],
                    "findings": result["findings"],
                }

            return self._start_task("scan", task)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(str, result=str)
    def start_lab(self, config_json: str) -> str:
        try:
            cfg = json.loads(config_json) if config_json else {}

            def task():
                result = run_lab(clean_files=int(cfg.get("clean_files") or 200))
                self._last_scan = {
                    "stats": result["stats"],
                    "meta": result["meta"],
                    "findings": result["findings"],
                    "planted": result.get("planted"),
                    "lab_hits": result.get("lab_hits"),
                    "lab_total": result.get("lab_total"),
                }
                return {
                    "ok": True,
                    "stats": result["stats"],
                    "meta": result["meta"],
                    "findings": result["findings"],
                    "planted": result.get("planted"),
                    "lab_hits": result.get("lab_hits"),
                    "lab_total": result.get("lab_total"),
                }

            return self._start_task("lab", task)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(result=str)
    def get_last_results(self) -> str:
        if not self._last_scan:
            return json.dumps({"ok": True, "empty": True})
        return json.dumps({"ok": True, "empty": False, **self._last_scan}, ensure_ascii=False)

    @Slot(str, result=str)
    def export_report(self, kind: str) -> str:
        if not self._last_scan or not self._last_scan.get("findings"):
            return json.dumps({"ok": False, "error": "No hay resultados para exportar"})

        parent = self.parent()
        if kind == "json":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar JSON", "heimdall-informe.json", "JSON (*.json)"
            )
        elif kind == "csv":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar CSV", "heimdall-hallazgos.csv", "CSV (*.csv)"
            )
        elif kind == "html":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar HTML", "heimdall-informe.html", "HTML (*.html)"
            )
        else:
            return json.dumps({"ok": False, "error": "Formato no soportado"})

        if not path:
            return json.dumps({"ok": False, "cancelled": True})

        try:
            from heimdall_timewatch.detector import FileVerdict, Finding

            verdicts = []
            for item in self._last_scan["findings"]:
                verdict = FileVerdict(
                    record_number=item["record_number"],
                    filename=item.get("filename"),
                    is_directory=item.get("is_directory", False),
                    in_use=item.get("in_use", True),
                    score=item.get("score", 0),
                )
                for f in item.get("findings", []):
                    verdict.findings.append(
                        Finding(
                            code=f["code"],
                            title=f["title"],
                            confidence=f["confidence"],
                            detail=f["detail"],
                            false_positive_note=f.get("false_positive_note", ""),
                        )
                    )
                verdicts.append(verdict)

            stats = self._last_scan["stats"]
            meta = self._last_scan.get("meta") or {}
            if kind == "json":
                export_json(verdicts, stats, path, meta)
            elif kind == "csv":
                export_csv(verdicts, path)
            else:
                export_html(verdicts, stats, path, meta)
            return json.dumps({"ok": True, "path": path})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(str, result=str)
    def ai_chat(self, message: str) -> str:
        try:
            settings = get_all_settings()

            def task():
                return chat_message(message, settings)

            return self._start_task("chat", task)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc), "content": ""})

    @Slot(result=str)
    def ai_analyze_scan(self) -> str:
        if not self._last_scan:
            return json.dumps({"ok": False, "error": "Ejecuta un análisis primero"})

        try:
            settings = get_all_settings()
            payload = dict(self._last_scan)

            def task():
                return analyze_findings(payload, settings)

            return self._start_task("analyze", task)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc), "content": ""})

    @Slot(str, str, result=str)
    def export_ai_summary(self, content: str, kind: str) -> str:
        text = (content or "").strip()
        if not text:
            return json.dumps({"ok": False, "error": "No hay contenido para exportar"})

        parent = self.parent()
        if kind == "html":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar resumen IA", "heimdall-resumen-ia.html", "HTML (*.html)"
            )
        elif kind == "md":
            path, _ = QFileDialog.getSaveFileName(
                parent, "Exportar resumen IA", "heimdall-resumen-ia.md", "Markdown (*.md)"
            )
        else:
            return json.dumps({"ok": False, "error": "Formato no soportado"})

        if not path:
            return json.dumps({"ok": False, "cancelled": True})

        try:
            meta = dict((self._last_scan or {}).get("meta") or {})
            settings = get_all_settings()
            provider = settings.get("ollama_provider", "local")
            model = (
                settings.get("ollama_cloud_model")
                if provider == "cloud"
                else settings.get("ollama_model")
            )
            if model:
                meta.setdefault("model", model)
            if kind == "html":
                export_ai_html(text, path, meta=meta)
            else:
                Path(path).write_text(text, encoding="utf-8")
            return json.dumps({"ok": True, "path": path})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @Slot(str, result=str)
    def reveal_path(self, path: str) -> str:
        import os
        import subprocess
        import sys

        target = Path(path)
        if not target.exists():
            return json.dumps({"ok": False, "error": "Ruta no encontrada"})
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", str(target.resolve())], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", str(target.resolve())], check=False)
            else:
                subprocess.run(["xdg-open", str(target.parent.resolve())], check=False)
            return json.dumps({"ok": True})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)})
