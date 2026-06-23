"""Punto de entrada del panel Windows."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.ui.main_window import MainWindow
from gui.ui.splash import HeroSplashScreen, SplashScreen, hero_video_path
from gui.ui.window_layout import apply_geometry, capture_frame_geometry


def apply_light_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#eef2ff"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3b82f6"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("heimdall-timewatch")
    app.setOrganizationName("Heimdall")
    app.setApplicationDisplayName("heimdall-timewatch")
    app.setFont(QFont("Segoe UI", 10))
    apply_light_palette(app)

    splash: HeroSplashScreen | SplashScreen | None = None
    window: MainWindow | None = None
    saved_geo: tuple[int, int, int, int] | None = None

    def remember_splash_geometry() -> None:
        nonlocal saved_geo
        if splash is not None:
            saved_geo = capture_frame_geometry(splash)

    def open_main_window() -> None:
        nonlocal window
        if splash is not None:
            splash.close()
        window = MainWindow()
        if saved_geo is not None:
            apply_geometry(window, *saved_geo)
        window.show()
        window.raise_()
        window.activateWindow()
        window.setFocus()

    video = hero_video_path()
    if video.is_file():
        try:
            splash = HeroSplashScreen(video)
            splash.shown.connect(remember_splash_geometry)
            splash.finished.connect(open_main_window)
            splash.start()
        except Exception:
            splash = None

    if splash is None:
        splash = SplashScreen()
        splash.finished.connect(open_main_window)
        splash.set_message("Cargando dashboard forense...")
        splash.start()
        app.processEvents()
        QTimer.singleShot(1600, splash.close_and_finish)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
