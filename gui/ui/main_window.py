"""Ventana principal — shell QWebEngine."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from gui.ui.bridge import Bridge
from gui.ui.window_layout import fit_window_to_screen


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = project_root()
WEB_DIR = PROJECT_ROOT / "gui" / "ui" / "web"


def _enable_dark_titlebar(window) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        value = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Heimdall Timewatch — TimeStomp Detector")
        self.setMinimumSize(960, 640)

        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)

        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
        )

        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self.channel = QWebChannel(self.view.page())
        self.bridge = Bridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        index = WEB_DIR / "index.html"
        self.view.load(QUrl.fromLocalFile(str(index.resolve())))

        fit_window_to_screen(self)
        _enable_dark_titlebar(self)
