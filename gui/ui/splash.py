"""Splash / hero de inicio con vídeo de marca + audio."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from gui.ui.window_layout import fit_window_to_screen

HERO_VIDEO_NAME = "Heimdall-Timewatch.mp4"
HERO_VIDEO_FALLBACK = "Heimdall-Timewatch_logo_animation_202606231734.mp4"


def _package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


def hero_video_path() -> Path:
    """Ruta al MP4 del hero (assets empaquetados o raíz del repo en dev)."""
    assets_dir = Path(__file__).resolve().parent / "assets"
    repo_root = _package_root().parent

    for name in (HERO_VIDEO_NAME, HERO_VIDEO_FALLBACK):
        for base in (assets_dir, repo_root):
            candidate = base / name
            if candidate.is_file():
                return candidate
    return assets_dir / HERO_VIDEO_NAME


def center_on_screen(widget: QWidget) -> None:
    fit_window_to_screen(widget)


class HeroSplashScreen(QWidget):
    """Reproduce el vídeo de marca al mismo tamaño que la ventana principal."""

    finished = Signal()
    shown = Signal()

    def __init__(
        self,
        video_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._closing = False
        self._playback_started = False
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background: #08080a;")

        self.video_widget = QVideoWidget(self)
        self.video_widget.setStyleSheet("background: #000;")
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        self.video_widget.setGeometry(0, 0, 960, 640)

        self.skip_label = QLabel("Clic o Esc para omitir", self.video_widget)
        self.skip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skip_label.setStyleSheet(
            "color: rgba(248,250,252,0.5); font-size: 11px; padding: 8px 12px;"
            "background: rgba(8,8,10,0.55); border-radius: 8px;"
        )
        self.skip_label.adjustSize()

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(1.0)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.setSource(QUrl.fromLocalFile(str(video_path.resolve())))

        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_error)

    def _layout_chrome(self) -> None:
        w, h = self.width(), self.height()
        self.video_widget.setGeometry(0, 0, w, h)

        self.skip_label.adjustSize()
        self.skip_label.move(
            max(12, (w - self.skip_label.width()) // 2),
            max(12, h - self.skip_label.height() - 16),
        )
        self.skip_label.raise_()

    def resizeEvent(self, event) -> None:
        self._layout_chrome()
        super().resizeEvent(event)

    def _begin_playback(self) -> None:
        if self._playback_started or self._closing:
            return
        self._playback_started = True
        self.player.play()

    def start(self) -> None:
        fit_window_to_screen(self)
        self._layout_chrome()
        self.show()
        self.raise_()
        self.activateWindow()
        self.shown.emit()
        status = self.player.mediaStatus()
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._begin_playback()

    def _finish(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.player.stop()
        self.finished.emit()
        self.close()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._begin_playback()
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()

    def _on_error(self, *_args) -> None:
        self._finish()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self._finish()
        super().mousePressEvent(event)


class SplashScreen(QWidget):
    """Fallback estático si no hay vídeo o falla Qt Multimedia."""

    finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(440, 220)
        self.setStyleSheet(
            """
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 rgba(255,255,255,0.95), stop:1 rgba(238,242,255,0.98));
                color: #0f172a;
                border: 1px solid rgba(255,255,255,0.9);
                border-radius: 20px;
            }
            QLabel#title { font-size: 22px; font-weight: 700; color: #3b82f6; }
            QLabel#sub { font-size: 11px; color: #64748b; letter-spacing: 1.5px; }
            QProgressBar {
                background: rgba(148,163,184,0.2);
                border: none; border-radius: 4px; height: 6px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #60a5fa, stop:1 #3b82f6);
                border-radius: 4px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)

        title = QLabel("Heimdall Timewatch")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))

        subtitle = QLabel("DFIR · TIMESTOMP DETECTION")
        subtitle.setObjectName("sub")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel("Inicializando panel forense...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #334155; font-size: 12px;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)

        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()
        layout.addWidget(self.status)
        layout.addWidget(self.progress)

    def set_message(self, message: str) -> None:
        self.status.setText(message)

    def start(self) -> None:
        center_on_screen(self)
        self.show()

    def close_and_finish(self) -> None:
        self.finished.emit()
        self.close()
