"""Geometría compartida ventana principal / hero splash."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


def fit_window_to_screen(window: QWidget) -> None:
    """Misma lógica de tamaño y centrado que la ventana principal."""
    screen = QGuiApplication.primaryScreen()
    if not screen:
        window.resize(1280, 820)
        return
    available = screen.availableGeometry()
    width = max(960, min(1440, available.width() - 48))
    height = max(640, min(900, available.height() - 48))
    window.resize(width, height)
    frame = window.frameGeometry()
    frame.moveCenter(available.center())
    window.move(frame.topLeft())


def apply_matching_geometry(target: QWidget, reference: QWidget) -> None:
    """Iguala posición y tamaño exterior al widget de referencia (p. ej. MainWindow)."""
    x, y, w, h = capture_frame_geometry(reference)
    apply_geometry(target, x, y, w, h)
    target.setFixedSize(w, h)


def apply_geometry(window: QWidget, x: int, y: int, width: int, height: int) -> None:
    """Restaura posición y tamaño (p. ej. tras el splash hero)."""
    window.resize(width, height)
    window.move(x, y)


def capture_frame_geometry(widget: QWidget) -> tuple[int, int, int, int]:
    """Captura x, y, ancho y alto exterior de un widget."""
    geo = widget.frameGeometry()
    return geo.x(), geo.y(), geo.width(), geo.height()
