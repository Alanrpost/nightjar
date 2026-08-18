"""Tray icon + main window: import from clipboard/QR, profile list, connect/disconnect,
kill switch, auto-reconnect, autostart, connection test, profile backup/restore."""

from __future__ import annotations

import ctypes
import dataclasses
import subprocess
import threading
import time

from PySide6.QtCore import (
    Qt,
    QByteArray,
    QEasingCurve,
    QLibraryInfo,
    QRectF,
    QSize,
    QTimer,
    QTranslator,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QColor,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGraphicsDropShadowEffect,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QLabel,
    QHBoxLayout,
)

from . import autostart, geoip, i18n, paths, profile_store, settings, subscription, updater
from .i18n import t
from .edit_profile_dialog import EditProfileDialog
from .json_edit_dialog import JsonEditDialog
from .qr_import import decode_qr_from_file, decode_qr_from_qimage
from .singbox_config import CLASH_API_ADDRESS
from .singbox_manager import GRACEFUL_STOP_TIMEOUT, SingBoxManager
from .split_tunnel_dialog import SplitTunnelDialog
from .stats import fetch_traffic, format_bytes, format_duration
from .profile_parser import Profile, ProfileParseError, looks_like_profile_uri, parse_profile_uri

APP_NAME = "Nightjar"
APP_VERSION = "1.4.0"

STATUS_TICK_MS = 1000
RECONNECT_DELAYS_MS = [3000, 6000, 12000, 24000, 30000]

KEBAB_ICON_SIZE = QSize(24, 24)
PASTE_ICON_SIZE = QSize(20, 20)
SPEED_ICON_SIZE = QSize(20, 20)
QR_ICON_SIZE = QSize(20, 20)
SPLIT_TUNNEL_ICON_SIZE = QSize(20, 20)


def _speed_test_idle_text() -> str:
    return f" {t('speed_test_idle')}"

TOGGLE_WIDTH = 46
TOGGLE_HEIGHT = 26
LOG_EXPORT_TAIL_BYTES = 2 * 1024 * 1024

# Palette - "Graphite": monochrome silver pulled from the logo, so app chrome and
# icon read as one product. Color is reserved almost entirely for connection-state
# signaling (connecting/connected/error) - everything else stays grayscale.
BG_APP = "#0C0C0E"
BG_CARD = "#19191D"
BG_CARD_ALT = "#1D1D21"
BG_ACTIVE = "#232328"
BORDER = "#26262B"
BORDER_FOCUS = "#3A3A41"
TEXT_PRIMARY = "#ECEDEF"
TEXT_MUTED = "#8A9099"
TEXT_DISABLED = "#55585F"
ACCENT = "#C7CCD6"
ACCENT_HOVER = "#DDE1E8"
ACCENT_SOFT = "rgba(199, 204, 214, 0.14)"
ACCENT_TEXT_ON = "#0C0C0E"
ERROR = "#E24B4A"
WARNING = "#e67e22"
CONNECTING = "#F4B84C"
CONNECTED = "#4ADE80"
DISCONNECTED = "#5C5F66"

APP_STYLESHEET = f"""
QWidget {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}
QMainWindow, QDialog, QMessageBox {{
    background-color: {BG_APP};
}}
QLabel {{
    background: transparent;
}}
QPushButton {{
    background-color: {BG_CARD_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {BG_ACTIVE};
    border-color: {ACCENT_HOVER};
}}
QPushButton:pressed {{
    background-color: {BG_CARD};
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
}}
QCheckBox {{
    spacing: 8px;
    background: transparent;
    padding: 4px 0;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {BG_CARD_ALT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {BORDER_FOCUS};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QListWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{
    border-bottom: 1px solid {BORDER};
}}
QListWidget::item:selected {{
    background-color: {BG_ACTIVE};
}}
QMenu {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT_ON};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_HOVER};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""

ICON_BUTTON_STYLESHEET = f"""
QPushButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
}}
QPushButton:hover {{
    background: {BG_CARD_ALT};
}}
"""

LANGUAGE_BUTTON_STYLESHEET = f"""
QPushButton {{
    padding: 6px 16px;
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: {BG_CARD_ALT};
    color: {TEXT_MUTED};
}}
QPushButton:hover {{
    border-color: {ACCENT_HOVER};
}}
QPushButton:checked {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT};
    color: {ACCENT};
    font-weight: 600;
}}
"""


_ICON_SUPERSAMPLE = 4


def _new_supersampled_painter(size: int) -> tuple[QPixmap, QPainter]:
    """Blank pixmap rendered at _ICON_SUPERSAMPLE x the target size, then downscaled
    with smooth filtering in _finish_supersampled(). Relying on devicePixelRatio
    metadata to get crisp icons turned out not to be enough - on this app, windows
    launched elevated (UAC "runas") still ended up jagged despite the process
    correctly reporting Per-Monitor-V2 DPI awareness and the right scale factor to
    Qt (confirmed via logging), for reasons that trace back to how DWM composites
    elevated windows rather than anything in this process's own DPI setup. Doing
    our own anti-aliasing via supersample-then-downscale sidesteps that entirely:
    the source pixmap is already smooth before it ever reaches window composition,
    so it stays smooth regardless of what happens after.
    Painter is pre-scaled by the supersample factor, so callers keep drawing in
    plain `size`-sized logical coordinates."""
    big = size * _ICON_SUPERSAMPLE
    pixmap = QPixmap(big, big)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(_ICON_SUPERSAMPLE, _ICON_SUPERSAMPLE)
    return pixmap, painter


def _finish_supersampled(pixmap: QPixmap, size: int, dpr: float = 1.0) -> QPixmap:
    # Downscale to size*dpr *physical* pixels and tag the result with dpr, so a
    # widget on a scaled display (e.g. 125%) doesn't have to stretch a flat 1x
    # pixmap to fill its actual (larger) backing store - that stretch is what
    # produces the soft/blurry look, no matter how clean the source was.
    physical = max(1, round(size * dpr))
    result = pixmap.scaled(
        physical, physical,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if dpr != 1.0:
        result.setDevicePixelRatio(dpr)
    return result


def _make_tray_icon(status_color: str) -> QIcon:
    """Rune ICO with a small colored status dot in the bottom-right corner."""
    ico_path = paths.assets_dir() / "icon.ico"
    base = QPixmap(str(ico_path)).scaled(
        32, 32,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(32, 32)
    result.fill(QColor(0, 0, 0, 0))
    painter = QPainter(result)
    painter.drawPixmap(0, 0, base)
    # Status dot — bottom-right corner
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(status_color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(21, 21, 10, 10)
    painter.end()
    return QIcon(result)


# Kept alive at module scope - QApplication.installTranslator() only holds a
# weak reference, so a local QTranslator would get garbage-collected right
# after this function returns and silently stop translating.
_qt_translator: QTranslator | None = None


def _apply_qt_translations(language: str) -> None:
    """Standard dialog buttons (Save/Cancel/OK/Yes/No, ...) are drawn by Qt
    itself, not by our own t() strings - they need Qt's own bundled .qm
    translation loaded to not show up in English regardless of app language."""
    global _qt_translator
    app = QApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if language == "en":
        return
    translator = QTranslator()
    translations_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(f"qtbase_{language}", translations_dir):
        app.installTranslator(translator)
        _qt_translator = translator


_THEMED_SVG_CACHE: dict[str, str] = {}


def _draw_themed_icon(filename: str, color: str, size: int = 20, dpr: float = 1.0) -> QPixmap:
    """Load a `{color}`-templated SVG from assets/ and render it tinted to match
    the surrounding UI (these used to ship with a hardcoded near-white fill,
    which read as an odd, brighter outlier next to the muted-gray icons
    everywhere else)."""
    template = _THEMED_SVG_CACHE.get(filename)
    if template is None:
        template = (paths.assets_dir() / filename).read_text(encoding="utf-8")
        _THEMED_SVG_CACHE[filename] = template
    svg_data = template.replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap, painter = _new_supersampled_painter(size)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return _finish_supersampled(pixmap, size, dpr)


_SETTINGS_ICON_TEMPLATE = (paths.assets_dir() / "settings_icon.svg").read_text(encoding="utf-8")


def _draw_settings_icon(color: str, size: int = 18, dpr: float = 1.0) -> QPixmap:
    svg_data = _SETTINGS_ICON_TEMPLATE.replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap, painter = _new_supersampled_painter(size)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return _finish_supersampled(pixmap, size, dpr)


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


TOGGLE_TRACK_OFF = "#2A2B31"
TOGGLE_THUMB_MARGIN = 3.0
# Extra transparent padding around the visible pill, baked into the widget's
# own bounding box. QGraphicsDropShadowEffect gets clipped to its widget's
# rect, so without this margin the hover glow was cut off in a visible flat
# edge right at the pill's silhouette instead of fading out softly.
TOGGLE_GLOW_MARGIN = 10.0


class ToggleSwitch(QPushButton):
    """Compact pill-shaped connect/disconnect switch: a capsule track with a
    sliding thumb, tinted by the current connection state color and animated
    between its off (left) and on (right) positions."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_color = QColor(ACCENT)
        self._on = False
        self._slide = 0.0  # 0 = off/left, 1 = on/right
        self._hover_progress = 0.0
        self._track_pixmap: QPixmap | None = None
        self._slide_anim = QVariantAnimation(self)
        self._slide_anim.setDuration(180)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide_anim.valueChanged.connect(self._on_slide_anim_value)
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_anim_value)
        self._glow_effect = QGraphicsDropShadowEffect(self)
        self._glow_effect.setOffset(0, 0)
        self._glow_effect.setBlurRadius(0)
        self.setGraphicsEffect(self._glow_effect)
        self.setFlat(True)
        # Same reasoning as elsewhere in this file: the app-level QPushButton rule
        # sets min-height, which fights a plain setFixedSize() once the widget is
        # polished - pin all four bounds on the widget's own stylesheet instead.
        # The pinned size includes TOGGLE_GLOW_MARGIN of transparent padding on
        # every side, so the widget's real footprint is bigger than the pill
        # actually painted at its center - see TOGGLE_GLOW_MARGIN above.
        full_w = TOGGLE_WIDTH + TOGGLE_GLOW_MARGIN * 2
        full_h = TOGGLE_HEIGHT + TOGGLE_GLOW_MARGIN * 2
        self.setStyleSheet(
            f"QPushButton {{"
            f"    border: none;"
            f"    background: transparent;"
            f"    padding: 0px;"
            f"    min-width: {full_w}px;"
            f"    max-width: {full_w}px;"
            f"    min-height: {full_h}px;"
            f"    max-height: {full_h}px;"
            f"}}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, color: str, on: bool) -> None:
        self._state_color = QColor(color)
        if on != self._on:
            self._on = on
            self._slide_anim.stop()
            self._slide_anim.setStartValue(self._slide)
            self._slide_anim.setEndValue(1.0 if on else 0.0)
            self._slide_anim.start()
        else:
            self._rebuild()

    def refresh(self) -> None:
        """Re-render at the widget's current devicePixelRatioF(). A window's real
        DPI association can settle later than construction time - most reliably
        seen on elevated (UAC) launches - so callers re-invoke this once the
        window is actually on screen instead of trusting the value read earlier."""
        self._rebuild()

    def _on_slide_anim_value(self, value) -> None:
        self._slide = float(value)
        self._rebuild()

    def _on_hover_anim_value(self, value) -> None:
        self._hover_progress = float(value)
        self._rebuild()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().enterEvent(event)
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0)
        self._hover_anim.start()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().leaveEvent(event)
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(0.0)
        self._hover_anim.start()

    def _rebuild(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        self._track_pixmap = self._build_track_pixmap(self._state_color, dpr)
        glow_color = QColor(self._state_color)
        glow_color.setAlpha(round(160 * self._hover_progress))
        self._glow_effect.setColor(glow_color)
        self._glow_effect.setBlurRadius(14 * self._hover_progress)
        self.update()

    def _build_track_pixmap(self, color: QColor, dpr: float) -> QPixmap:
        """Track, border and thumb composed into one pre-antialiased pixmap per
        frame - same supersample-then-downscale approach as the rest of this
        file's hand-drawn widgets, just sized for a w != h capsule instead of a
        square icon, so it can't go through _new_supersampled_painter()/
        _finish_supersampled() (both assume a square). Canvas is the widget's
        full padded size (TOGGLE_GLOW_MARGIN on every side); the pill itself is
        drawn inset by that margin so it lands centered in the widget."""
        w = TOGGLE_WIDTH + TOGGLE_GLOW_MARGIN * 2
        h = TOGGLE_HEIGHT + TOGGLE_GLOW_MARGIN * 2
        big = QPixmap(round(w * _ICON_SUPERSAMPLE), round(h * _ICON_SUPERSAMPLE))
        big.fill(Qt.GlobalColor.transparent)
        painter = QPainter(big)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(_ICON_SUPERSAMPLE, _ICON_SUPERSAMPLE)
        painter.translate(TOGGLE_GLOW_MARGIN, TOGGLE_GLOW_MARGIN)

        pill_w, pill_h = TOGGLE_WIDTH, TOGGLE_HEIGHT
        off_color = QColor(TOGGLE_TRACK_OFF)
        track_color = _lerp_color(off_color, color, self._slide)
        border_color = QColor(color)
        border_color.setAlpha(round(90 + 130 * max(self._slide, self._hover_progress * 0.3)))

        radius = pill_h / 2
        track_rect = QRectF(0.75, 0.75, pill_w - 1.5, pill_h - 1.5)
        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        thumb_d = pill_h - TOGGLE_THUMB_MARGIN * 2
        travel = pill_w - thumb_d - TOGGLE_THUMB_MARGIN * 2
        thumb_x = TOGGLE_THUMB_MARGIN + travel * self._slide
        thumb_color = _lerp_color(color, QColor("#F5F6F8"), self._slide)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(QRectF(thumb_x, TOGGLE_THUMB_MARGIN, thumb_d, thumb_d))

        painter.end()
        physical_w = max(1, round(w * dpr))
        physical_h = max(1, round(h * dpr))
        result = big.scaled(
            physical_w, physical_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if dpr != 1.0:
            result.setDevicePixelRatio(dpr)
        return result

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._track_pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(
            QRectF(self.rect()), self._track_pixmap, QRectF(self._track_pixmap.rect())
        )
        painter.end()


class MainWindow(QMainWindow):
    # SingBoxManager's watchdog calls on_exit from a background thread; emitting a
    # signal (instead of touching widgets directly) marshals the call back onto the
    # Qt main thread via a queued connection.
    singbox_exited = Signal(int)
    connection_test_result = Signal(str)
    exit_ip_result = Signal(int, str, str)
    subscription_import_result = Signal(object)
    update_check_result = Signal(object)
    update_download_result = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(520, 460)
        self.setMinimumSize(440, 380)

        self.icon_disconnected = _make_tray_icon(DISCONNECTED)
        self.icon_connected = _make_tray_icon(CONNECTED)
        self.icon_error = _make_tray_icon(ERROR)
        self.icon_connecting = _make_tray_icon(CONNECTING)

        _ico_path = str(paths.assets_dir() / "icon.ico")
        self.setWindowIcon(QIcon(_ico_path))

        self.settings = settings.load_settings()
        i18n.set_language(self.settings.language)
        _apply_qt_translations(self.settings.language)

        self.manager = SingBoxManager(on_exit=self.singbox_exited.emit)
        self.singbox_exited.connect(self._on_singbox_exit)
        self.connection_test_result.connect(self._show_connection_test_result)
        self.exit_ip_result.connect(self._show_exit_ip_result)
        self.subscription_import_result.connect(self._show_subscription_import_result)
        self.update_check_result.connect(self._show_update_available)
        self.update_download_result.connect(self._show_update_download_result)

        self.profiles = profile_store.load_profiles()
        self.active_profile_name: str | None = None
        self.selected_profile_name: str | None = None
        self.connected_since: float | None = None
        self.kill_switch_active = False
        self.pending_reconnect_profile_name: str | None = None
        self.reconnect_attempt = 0
        self._connect_action_is_disconnect = False
        self._ip_lookup_generation = 0
        self._last_ip_country: tuple[str, str] | None = None

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self._reconnect_tick)

        self._add_menu_buttons: list[QPushButton] = []
        self._add_menu_action_specs: list[tuple] = []
        self._last_status_args: tuple[bool, bool, bool, bool] = (False, False, False, False)

        self.setCentralWidget(self._build_content())

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._tick)
        self.status_timer.start(STATUS_TICK_MS)

        self._refresh_profile_list()
        self._show_page(0)

        self.tray = QSystemTrayIcon(self.icon_disconnected, self)
        self.tray.setToolTip(t("tray_tooltip_disconnected", app=APP_NAME))
        tray_menu_actions = self._build_tray_menu()
        self.tray.setContextMenu(tray_menu_actions)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self._set_status(connected=False)
        self._enable_dark_titlebar()

        if self.settings.auto_connect_on_launch and self.settings.last_active_profile:
            profile = next(
                (p for p in self.profiles if p.name == self.settings.last_active_profile), None
            )
            if profile is not None:
                QTimer.singleShot(500, lambda: self._do_connect(profile, manual=False))

        QTimer.singleShot(3000, self._check_for_updates)

    def _enable_dark_titlebar(self) -> None:
        # Cosmetic only - if unsupported (older Windows 10 builds), just skip it.
        try:
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
            )
        except OSError:
            pass

    def _refresh_settings_icon(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        icon = QIcon(_draw_settings_icon(TEXT_MUTED, 18, dpr))
        self.settings_footer_btn.setIcon(icon)
        self.settings_back_btn.setIcon(
            QIcon(_draw_themed_icon("back_icon.svg", TEXT_MUTED, 18, dpr))
        )

    def _open_settings(self) -> None:
        self._show_page(1)

    def _close_settings(self) -> None:
        self._show_page(0)

    def _refresh_dpi_dependent_icons(self) -> None:
        """Re-render our own hand-drawn icons (settings icons, connect toggle)
        at the window's actual devicePixelRatioF(). Called once from
        showEvent() and once more shortly after on a timer, because on this
        app that value was observed to sometimes only settle to its correct
        scaled value a moment after the window is first shown - most reliably
        reproduced when launched elevated (UAC "runas")."""
        self._refresh_settings_icon()
        self.connect_toggle.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._refresh_dpi_dependent_icons()
        QTimer.singleShot(400, self._refresh_dpi_dependent_icons)

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(18)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_main_page())
        self.pages.addWidget(self._build_settings_page())
        layout.addWidget(self.pages, 1)

        return content

    def _build_add_menu_button(self) -> QPushButton:
        # Plain global QPushButton style - same look as the Settings button, no
        # special accent border.
        btn = QPushButton(f" {t('btn_add')}")
        menu = QMenu(btn)

        dpr = self.devicePixelRatioF() or 1.0
        paste_action = menu.addAction(
            QIcon(_draw_themed_icon("paste_icon.svg", TEXT_MUTED, 20, dpr)),
            t("menu_import_clipboard"),
        )
        paste_action.triggered.connect(self.import_from_clipboard)

        qr_action = menu.addAction(
            QIcon(_draw_themed_icon("qr_icon.svg", TEXT_MUTED, 20, dpr)), t("menu_import_qr")
        )
        qr_action.triggered.connect(self.import_from_qr_file)

        manual_action = menu.addAction(
            QIcon(_draw_themed_icon("add_icon.svg", TEXT_MUTED, 20, dpr)), t("menu_import_manual")
        )
        manual_action.triggered.connect(self.add_profile_manually)

        self._add_menu_buttons.append(btn)
        self._add_menu_action_specs.extend([
            (paste_action, "menu_import_clipboard"),
            (qr_action, "menu_import_qr"),
            (manual_action, "menu_import_manual"),
        ])

        # Show the menu manually instead of QPushButton.setMenu() - setMenu() draws
        # its own dropdown-arrow indicator next to the text, which we don't want.
        btn.clicked.connect(
            lambda _checked=False, b=btn, m=menu: m.exec(b.mapToGlobal(b.rect().bottomLeft()))
        )
        return btn

    def _build_main_page(self) -> QWidget:
        """Header: status (left) + connect toggle (right). Stats row: time /
        traffic / IP as three columns. Profile list fills the rest. Footer:
        Settings (left) ... Add (right)."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        self.status_text = QLabel(t("status_idle"))
        self.status_text.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.status_text.setWordWrap(True)
        header_row.addWidget(self.status_text, 1)

        self.connect_toggle = ToggleSwitch()
        self.connect_toggle.clicked.connect(self._on_connect_button_clicked)
        header_row.addWidget(self.connect_toggle, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(header_row)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(20)

        self.time_label = QLabel()
        self.time_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.time_label.setFixedHeight(16)
        stats_row.addWidget(self.time_label, 1)

        self.traffic_label = QLabel()
        self.traffic_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.traffic_label.setFixedHeight(16)
        stats_row.addWidget(self.traffic_label, 1)

        self.ip_label = QLabel()
        self.ip_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.ip_label.setFixedHeight(16)
        stats_row.addWidget(self.ip_label, 1)

        layout.addLayout(stats_row)

        self.profile_list = QListWidget()
        self._row_checkboxes: dict[str, QCheckBox] = {}
        layout.addWidget(self.profile_list, 1)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(12)

        self.settings_footer_btn = QPushButton(f" {t('nav_settings')}")
        self.settings_footer_btn.setIconSize(QSize(18, 18))
        self.settings_footer_btn.clicked.connect(self._open_settings)
        footer_row.addWidget(self.settings_footer_btn)

        footer_row.addStretch(1)

        add_btn = self._build_add_menu_button()
        footer_row.addWidget(add_btn)

        layout.addLayout(footer_row)

        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.settings_back_btn = QPushButton()
        self.settings_back_btn.setStyleSheet(ICON_BUTTON_STYLESHEET)
        self.settings_back_btn.setIconSize(QSize(18, 18))
        self.settings_back_btn.clicked.connect(self._close_settings)
        title_row.addWidget(self.settings_back_btn)

        self.settings_title_label = QLabel(t("settings_title"))
        self.settings_title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        title_row.addWidget(self.settings_title_label)
        title_row.addStretch(1)
        layout.addLayout(title_row)

        language_row = QHBoxLayout()
        self.language_row_label = QLabel(t("language_label"))
        language_row.addWidget(self.language_row_label)
        language_row.addSpacing(8)

        self._language_group = QButtonGroup(page)
        self._language_group.setExclusive(True)
        self.lang_ru_btn = QPushButton("Русский")
        self.lang_en_btn = QPushButton("English")
        for code, btn in (("ru", self.lang_ru_btn), ("en", self.lang_en_btn)):
            btn.setCheckable(True)
            btn.setStyleSheet(LANGUAGE_BUTTON_STYLESHEET)
            btn.setChecked(code == self.settings.language)
            btn.clicked.connect(lambda _checked=False, c=code: self._on_language_selected(c))
            self._language_group.addButton(btn)
            language_row.addWidget(btn)
        language_row.addStretch(1)
        layout.addLayout(language_row)

        self.kill_switch_checkbox = QCheckBox(t("kill_switch_label"))
        self.kill_switch_checkbox.setChecked(self.settings.kill_switch_enabled)
        self.kill_switch_checkbox.toggled.connect(self._on_kill_switch_toggled)
        layout.addWidget(self.kill_switch_checkbox)

        self.kill_switch_hint_label = QLabel()
        self.kill_switch_hint_label.setWordWrap(True)
        self.kill_switch_hint_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; margin-left: 24px;"
        )
        layout.addWidget(self.kill_switch_hint_label)
        self._update_kill_switch_hint()

        self.autostart_checkbox = QCheckBox(t("autostart_label"))
        try:
            self.autostart_checkbox.setChecked(autostart.is_enabled())
        except OSError:
            self.autostart_checkbox.setChecked(False)
        self.autostart_checkbox.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self.autostart_checkbox)

        self.auto_connect_checkbox = QCheckBox(t("auto_connect_label"))
        self.auto_connect_checkbox.setChecked(self.settings.auto_connect_on_launch)
        self.auto_connect_checkbox.toggled.connect(self._on_auto_connect_toggled)
        layout.addWidget(self.auto_connect_checkbox)

        dpr = self.devicePixelRatioF() or 1.0

        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self.split_tunnel_btn = QPushButton(f" {t('split_tunnel_btn')}")
        self.split_tunnel_btn.setIcon(
            QIcon(_draw_themed_icon("split_tunnel_icon.svg", TEXT_MUTED, 20, dpr))
        )
        self.split_tunnel_btn.setIconSize(SPLIT_TUNNEL_ICON_SIZE)
        self.split_tunnel_btn.clicked.connect(self.open_split_tunnel_settings)
        action_row.addWidget(self.split_tunnel_btn, 1)

        self.test_btn = QPushButton(_speed_test_idle_text())
        self.test_btn.setIcon(QIcon(_draw_themed_icon("speed_icon.svg", TEXT_MUTED, 20, dpr)))
        self.test_btn.setIconSize(SPEED_ICON_SIZE)
        self.test_btn.clicked.connect(self.test_connection)
        action_row.addWidget(self.test_btn, 1)

        layout.addLayout(action_row)

        self.export_logs_btn = QPushButton(f" {t('export_logs_btn')}")
        self.export_logs_btn.setIcon(
            QIcon(_draw_themed_icon("logs_icon.svg", TEXT_MUTED, 20, dpr))
        )
        self.export_logs_btn.setIconSize(QSize(20, 20))
        self.export_logs_btn.clicked.connect(self._export_logs)
        layout.addWidget(self.export_logs_btn)

        layout.addStretch(1)

        brand_label = QLabel(
            f'<span style="font-weight:700; font-size:13px;">{APP_NAME}</span>'
            f'&nbsp;&nbsp;<span style="color:{TEXT_MUTED}; font-size:11px;">'
            f"v{APP_VERSION}</span>"
        )
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_label)

        return page

    def _on_language_selected(self, language: str) -> None:
        if language == self.settings.language:
            return
        self.settings.language = language
        settings.save_settings(self.settings)
        i18n.set_language(language)
        _apply_qt_translations(language)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Re-apply text to every persistent widget after the language setting
        changes. Dialogs/menus built fresh each time they're opened don't need
        this - they read t() at construction and so already show the current
        language the next time they're shown."""
        self.settings_footer_btn.setText(f" {t('nav_settings')}")
        self.settings_title_label.setText(t("settings_title"))
        self.language_row_label.setText(t("language_label"))
        self.kill_switch_checkbox.setText(t("kill_switch_label"))
        self._update_kill_switch_hint()
        self.autostart_checkbox.setText(t("autostart_label"))
        self.auto_connect_checkbox.setText(t("auto_connect_label"))
        self.split_tunnel_btn.setText(f" {t('split_tunnel_btn')}")
        self.export_logs_btn.setText(f" {t('export_logs_btn')}")

        # Mid-test the button shows idle-text + "..."; anything else (enabled) is idle.
        was_testing = not self.test_btn.isEnabled()
        self.test_btn.setText(_speed_test_idle_text() + ("..." if was_testing else ""))

        for btn in self._add_menu_buttons:
            btn.setText(f" {t('btn_add')}")
        for action, key in self._add_menu_action_specs:
            action.setText(t(key))

        self.tray_show_action.setText(t("tray_open"))
        self.tray_connect_action.setText(t("tray_connect"))
        self.tray_disconnect_action.setText(t("tray_disconnect"))
        self.tray_quit_action.setText(t("tray_quit"))

        # Status text/tooltips/tray tooltip all depend on current connection state.
        self._set_status(*self._last_status_args)

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)

    def _build_tray_menu(self):
        menu = QMenu()
        self.tray_show_action = QAction(t("tray_open"), self)
        self.tray_show_action.triggered.connect(self.showNormal)
        menu.addAction(self.tray_show_action)

        self.tray_connect_action = QAction(t("tray_connect"), self)
        self.tray_connect_action.triggered.connect(self.connect_selected)
        menu.addAction(self.tray_connect_action)

        self.tray_disconnect_action = QAction(t("tray_disconnect"), self)
        self.tray_disconnect_action.triggered.connect(self.disconnect)
        menu.addAction(self.tray_disconnect_action)

        menu.addSeparator()
        self.tray_quit_action = QAction(t("tray_quit"), self)
        self.tray_quit_action.triggered.connect(self._quit)
        menu.addAction(self.tray_quit_action)
        return menu

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.activateWindow()

    def _refresh_profile_list(self) -> None:
        # Single profile: auto-select it. Multiple: keep the previous selection if
        # it still exists, otherwise nothing is selected until the user checks one.
        if len(self.profiles) == 1:
            self.selected_profile_name = self.profiles[0].name
        elif self.selected_profile_name not in {p.name for p in self.profiles}:
            self.selected_profile_name = None

        self.profile_list.clear()
        self._row_checkboxes = {}

        for profile in self.profiles:
            item = QListWidgetItem()
            self.profile_list.addItem(item)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)

            checkbox = QCheckBox()
            checkbox.setChecked(profile.name == self.selected_profile_name)
            checkbox.toggled.connect(
                lambda checked, name=profile.name: self._on_profile_checked(name, checked)
            )
            row_layout.addWidget(checkbox)

            label_text = f"{profile.name}  ({profile.host}:{profile.port})"
            if profile.raw_config.strip():
                label_text += "  [JSON]"
            row_layout.addWidget(QLabel(label_text), 1)

            menu_btn = QPushButton()
            menu_btn.setStyleSheet(ICON_BUTTON_STYLESHEET)
            menu_btn.setIcon(
                QIcon(_draw_themed_icon("kebab_icon.svg", TEXT_MUTED, 20, self.devicePixelRatioF() or 1.0))
            )
            menu_btn.setIconSize(KEBAB_ICON_SIZE)
            menu_btn.setFixedWidth(32)
            row_menu = QMenu(menu_btn)
            edit_json_action = row_menu.addAction(t("kebab_edit_json"))
            edit_json_action.triggered.connect(
                lambda _checked=False, name=profile.name: self._open_json_editor(name)
            )
            edit_profile_action = row_menu.addAction(t("kebab_edit_profile"))
            edit_profile_action.triggered.connect(
                lambda _checked=False, name=profile.name: self._edit_profile(name)
            )
            delete_action = row_menu.addAction(t("kebab_delete"))
            delete_action.triggered.connect(
                lambda _checked=False, name=profile.name: self._delete_profile(name)
            )
            # Show the menu manually instead of QPushButton.setMenu() - setMenu()
            # draws its own dropdown-arrow indicator next to the text, which we don't want.
            menu_btn.clicked.connect(
                lambda _checked=False, b=menu_btn, m=row_menu: m.exec(
                    b.mapToGlobal(b.rect().bottomLeft())
                )
            )
            row_layout.addWidget(menu_btn)

            self._row_checkboxes[profile.name] = checkbox
            item.setSizeHint(row.sizeHint())
            self.profile_list.setItemWidget(item, row)

    def _on_profile_checked(self, name: str, checked: bool) -> None:
        if checked:
            self.selected_profile_name = name
            for other_name, checkbox in self._row_checkboxes.items():
                if other_name != name and checkbox.isChecked():
                    checkbox.setChecked(False)
        elif self.selected_profile_name == name:
            self.selected_profile_name = None

    def _open_json_editor(self, profile_name: str) -> None:
        profile = next((p for p in self.profiles if p.name == profile_name), None)
        if profile is None:
            return

        dialog = JsonEditDialog(profile, self)
        if dialog.exec() != JsonEditDialog.DialogCode.Accepted:
            return
        if dialog.result_raw_config is None:
            return

        updated = dataclasses.replace(profile, raw_config=dialog.result_raw_config)
        was_active = profile.name == self.active_profile_name
        self.profiles = profile_store.update_profile(profile.name, updated)
        self._refresh_profile_list()

        if was_active:
            QMessageBox.information(
                self, t("dlg_config_changed_title"), t("dlg_reconnect_to_apply")
            )
            self.disconnect()

    def import_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text and (
            looks_like_profile_uri(text) or subscription.looks_like_subscription_url(text)
        ):
            self._import_text(text)
            return

        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            decoded = decode_qr_from_qimage(clipboard.image())
            if decoded:
                self._import_text(decoded)
                return

        QMessageBox.warning(
            self, t("dlg_import_failed_title"), t("dlg_import_failed_body")
        )

    def import_from_qr_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, t("file_dialog_qr_title"), "", t("file_dialog_images_filter")
        )
        if not path:
            return

        decoded = decode_qr_from_file(path)
        if not decoded:
            QMessageBox.warning(
                self, t("dlg_qr_not_recognized_title"), t("dlg_qr_not_recognized_body")
            )
            return
        self._import_text(decoded)

    def _import_text(self, text: str) -> None:
        text = text.strip()
        if subscription.looks_like_subscription_url(text):
            self._import_subscription(text)
            return

        try:
            profile = parse_profile_uri(text)
        except ProfileParseError as exc:
            QMessageBox.warning(self, t("dlg_import_failed_title"), str(exc))
            return

        self.profiles = profile_store.add_profile(profile)
        self._refresh_profile_list()
        QMessageBox.information(
            self, t("dlg_profile_imported_title"), t("dlg_profile_added_body", name=profile.name)
        )

    def _import_subscription(self, url: str) -> None:
        self.tray.showMessage(
            APP_NAME, t("tray_msg_subscription_importing"),
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )
        threading.Thread(
            target=self._run_subscription_import, args=(url,), daemon=True
        ).start()

    def _run_subscription_import(self, url: str) -> None:
        try:
            profiles = subscription.fetch_subscription_profiles(url)
            self.subscription_import_result.emit((profiles, None))
        except subscription.SubscriptionError as exc:
            self.subscription_import_result.emit((None, str(exc)))

    def _show_subscription_import_result(self, result: tuple) -> None:
        profiles, error = result
        if error is not None:
            QMessageBox.warning(self, t("dlg_import_failed_title"), error)
            return

        used_names = {p.name for p in self.profiles}
        for profile in profiles:
            name = profile.name
            suffix = 2
            while name in used_names:
                name = f"{profile.name} ({suffix})"
                suffix += 1
            profile.name = name
            used_names.add(name)
            self.profiles = profile_store.add_profile(profile)

        self._refresh_profile_list()
        QMessageBox.information(
            self,
            t("dlg_profile_imported_title"),
            t("dlg_subscription_imported_body", count=len(profiles)),
        )

    def _selected_profile(self):
        if not self.selected_profile_name:
            return None
        for profile in self.profiles:
            if profile.name == self.selected_profile_name:
                return profile
        return None

    def _on_connect_button_clicked(self) -> None:
        if self._connect_action_is_disconnect:
            self.disconnect()
        else:
            self.connect_selected()

    def connect_selected(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.warning(self, t("dlg_no_profile_title"), t("dlg_no_profile_body"))
            return

        self.reconnect_timer.stop()
        self.reconnect_attempt = 0
        self._do_connect(profile, manual=True)

    def _do_connect(self, profile: Profile, manual: bool) -> bool:
        self._set_status(connected=False, connecting=True)

        if self.manager.is_running:
            self.manager.stop()

        try:
            self.manager.start(
                profile,
                excluded_processes=self.settings.excluded_processes,
                split_tunnel_mode=self.settings.split_tunnel_mode,
                excluded_domains=self.settings.excluded_domains,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            if manual:
                QMessageBox.critical(self, t("dlg_connect_failed_title"), str(exc))
            self._engage_kill_switch_if_enabled()
            self._set_status(connected=False, error=True, kill_switch=self.kill_switch_active)
            return False

        self.active_profile_name = profile.name
        self.connected_since = time.monotonic()
        self.kill_switch_active = False
        self.reconnect_attempt = 0
        self.pending_reconnect_profile_name = None
        self.settings.last_active_profile = profile.name
        settings.save_settings(self.settings)
        self._set_status(connected=True)
        self._start_exit_ip_lookup()
        self.tray.showMessage(
            APP_NAME, t("tray_msg_connected", name=profile.name),
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )
        return True

    def _start_exit_ip_lookup(self) -> None:
        self._ip_lookup_generation += 1
        generation = self._ip_lookup_generation
        threading.Thread(
            target=self._run_exit_ip_lookup, args=(generation,), daemon=True
        ).start()

    def _run_exit_ip_lookup(self, generation: int) -> None:
        # Give the tunnel a moment to actually settle before routing a request
        # through it - right after connect, DNS/routes are sometimes still mid-setup,
        # which can reset the very first request. A couple of retries absorb that.
        time.sleep(1.5)
        result = None
        for attempt in range(3):
            if generation != self._ip_lookup_generation:
                return
            result = geoip.fetch_exit_ip_info()
            if result is not None:
                break
            if attempt < 2:
                time.sleep(2.0)
        if result is None:
            return
        ip, country = result
        self.exit_ip_result.emit(generation, ip, country)

    def _show_exit_ip_result(self, generation: int, ip: str, country: str) -> None:
        # Stale result from a connection that's since been superseded or dropped.
        if generation != self._ip_lookup_generation or self.active_profile_name is None:
            return
        self._last_ip_country = (ip, country)
        self.ip_label.setText(t("ip_label", value=f"{ip} · {country}"))

    def _engage_kill_switch_if_enabled(self) -> None:
        if not self.settings.kill_switch_enabled:
            self.kill_switch_active = False
            return
        try:
            self.manager.start_blockall(
                excluded_processes=self.settings.excluded_processes,
                split_tunnel_mode=self.settings.split_tunnel_mode,
                excluded_domains=self.settings.excluded_domains,
            )
            self.kill_switch_active = True
        except (FileNotFoundError, RuntimeError):
            self.kill_switch_active = False

    def disconnect(self) -> None:
        self.reconnect_timer.stop()
        self.pending_reconnect_profile_name = None
        self.reconnect_attempt = 0
        self.kill_switch_active = False
        self.manager.stop()
        self.active_profile_name = None
        self.connected_since = None
        self._set_status(connected=False)

    def _edit_profile(self, profile_name: str) -> None:
        profile = next((p for p in self.profiles if p.name == profile_name), None)
        if profile is None:
            return

        dialog = EditProfileDialog(profile, self)
        if dialog.exec() != EditProfileDialog.DialogCode.Accepted:
            return

        updated = dialog.result_profile
        if updated is None:
            return

        was_active = profile.name == self.active_profile_name
        try:
            self.profiles = profile_store.update_profile(profile.name, updated)
        except ValueError as exc:
            QMessageBox.warning(self, t("dlg_save_failed_title"), str(exc))
            return

        if self.selected_profile_name == profile.name:
            self.selected_profile_name = updated.name
        self._refresh_profile_list()

        if was_active:
            QMessageBox.information(
                self, t("dlg_profile_changed_title"), t("dlg_reconnect_to_apply")
            )
            self.disconnect()

    def _delete_profile(self, profile_name: str) -> None:
        profile = next((p for p in self.profiles if p.name == profile_name), None)
        if profile is None:
            return

        confirm = QMessageBox.question(
            self,
            t("dlg_delete_profile_title"),
            t("dlg_delete_profile_body", name=profile.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if profile.name == self.active_profile_name:
            self.disconnect()
        if profile.name == self.pending_reconnect_profile_name:
            self.reconnect_timer.stop()
            self.pending_reconnect_profile_name = None
        self.profiles = profile_store.remove_profile(profile.name)
        if self.selected_profile_name == profile.name:
            self.selected_profile_name = None
        self._refresh_profile_list()

    def add_profile_manually(self) -> None:
        blank_profile = Profile(name=t("default_new_profile_name"))
        dialog = EditProfileDialog(blank_profile, self)
        dialog.setWindowTitle(t("dlg_add_profile_title"))
        if dialog.exec() != EditProfileDialog.DialogCode.Accepted:
            return

        new_profile = dialog.result_profile
        if new_profile is None:
            return

        if any(p.name == new_profile.name for p in self.profiles):
            QMessageBox.warning(
                self,
                t("dlg_profile_exists_title"),
                t("dlg_profile_exists_body", name=new_profile.name),
            )
            return

        self.profiles = profile_store.add_profile(new_profile)
        self._refresh_profile_list()
        QMessageBox.information(
            self, t("dlg_profile_added_title"), t("dlg_profile_added_body", name=new_profile.name)
        )

    def test_connection(self) -> None:
        if self.active_profile_name is None:
            QMessageBox.information(
                self, t("dlg_not_connected_title"), t("dlg_not_connected_body")
            )
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(_speed_test_idle_text() + "...")
        threading.Thread(target=self._run_connection_test, daemon=True).start()

    def _run_connection_test(self) -> None:
        import io
        import sys

        # --noconsole builds set sys.stdout/stderr to None; speedtest-cli passes them
        # to subprocess.Popen which then crashes on .fileno(). Patch for the duration.
        _nul = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        if sys.stdout is None:
            sys.stdout = _nul
        if sys.stderr is None:
            sys.stderr = _nul
        try:
            import speedtest

            st = speedtest.Speedtest()
            st.get_best_server()
            download_mbps = st.download() / 1_000_000
            upload_mbps = st.upload() / 1_000_000
            ping_ms = st.results.ping
            self.connection_test_result.emit(f"OK:{ping_ms:.0f}:{download_mbps:.1f}:{upload_mbps:.1f}")
        except Exception as exc:  # speedtest-cli raises various custom + network exceptions
            self.connection_test_result.emit(f"FAIL:{exc}")
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    def _show_connection_test_result(self, result: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText(_speed_test_idle_text())

        if result.startswith("OK:"):
            _, ping_ms, download_mbps, upload_mbps = result.split(":")
            QMessageBox.information(
                self,
                t("dlg_speed_result_title"),
                t(
                    "dlg_speed_result_body",
                    ping=ping_ms, download=download_mbps, upload=upload_mbps,
                ),
            )
        else:
            QMessageBox.warning(
                self, t("dlg_speed_failed_title"), t("dlg_speed_failed_body", error=result[5:])
            )

    def open_split_tunnel_settings(self) -> None:
        dialog = SplitTunnelDialog(
            self.settings.excluded_processes,
            self.settings.split_tunnel_mode,
            self.settings.excluded_domains,
            self,
        )
        if dialog.exec() != SplitTunnelDialog.DialogCode.Accepted:
            return
        self.settings.excluded_processes = dialog.result_processes()
        self.settings.split_tunnel_mode = dialog.result_mode()
        self.settings.excluded_domains = dialog.result_domains()
        settings.save_settings(self.settings)
        self._update_kill_switch_hint()
        if self.active_profile_name is not None:
            QMessageBox.information(
                self,
                t("dlg_split_tunnel_changed_title"),
                t("dlg_split_tunnel_changed_body"),
            )

    def _export_logs(self) -> None:
        log_path = paths.log_file()
        if not log_path.exists():
            QMessageBox.information(self, t("dlg_no_logs_title"), t("dlg_no_logs_body"))
            return

        default_name = f"{APP_NAME.lower()}-logs.log"
        dest, _ = QFileDialog.getSaveFileName(
            self, t("export_logs_btn"), default_name, t("file_dialog_logs_filter")
        )
        if not dest:
            return

        try:
            # Only the recent tail - sing-box.log accumulates across every run
            # this app has ever made (can reach hundreds of MB), and what's
            # useful for diagnosing "what's wrong right now" is the last bit of
            # activity, not the whole history.
            size = log_path.stat().st_size
            with open(log_path, "rb") as src:
                if size > LOG_EXPORT_TAIL_BYTES:
                    src.seek(size - LOG_EXPORT_TAIL_BYTES)
                data = src.read()
            with open(dest, "wb") as out:
                out.write(data)
        except OSError as exc:
            QMessageBox.warning(self, t("dlg_logs_save_failed_title"), str(exc))
            return

        QMessageBox.information(
            self, t("dlg_logs_saved_title"), t("dlg_logs_saved_body", path=dest)
        )

    def _on_kill_switch_toggled(self, checked: bool) -> None:
        self.settings.kill_switch_enabled = checked
        settings.save_settings(self.settings)

    def _update_kill_switch_hint(self) -> None:
        key = (
            "kill_switch_hint_include"
            if self.settings.split_tunnel_mode == "include"
            else "kill_switch_hint"
        )
        text = t(key)
        self.kill_switch_hint_label.setText(text)

    def _on_auto_connect_toggled(self, checked: bool) -> None:
        self.settings.auto_connect_on_launch = checked
        settings.save_settings(self.settings)

    def _on_autostart_toggled(self, checked: bool) -> None:
        try:
            if checked:
                autostart.enable()
            else:
                autostart.disable()
        except (RuntimeError, OSError) as exc:
            QMessageBox.warning(self, t("dlg_autostart_error_title"), str(exc))
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not checked)
            self.autostart_checkbox.blockSignals(False)

    def _update_toggle_button(
        self, color: str, tooltip: str, disconnect_action: bool, on: bool
    ) -> None:
        self._connect_action_is_disconnect = disconnect_action
        self.connect_toggle.setToolTip(tooltip)
        self.connect_toggle.set_state(color, on)

    def _set_status(
        self,
        connected: bool,
        error: bool = False,
        kill_switch: bool = False,
        connecting: bool = False,
    ) -> None:
        self._last_status_args = (connected, error, kill_switch, connecting)

        if connecting:
            message = t("status_connecting")
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_connecting)
            self.tray.setToolTip(t("tray_tooltip_connecting", app=APP_NAME))
            self._update_toggle_button(CONNECTING, message, disconnect_action=False, on=True)
        elif kill_switch:
            message = t("status_killswitch")
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip(t("tray_tooltip_killswitch", app=APP_NAME))
            self._update_toggle_button(WARNING, message, disconnect_action=True, on=True)
        elif error:
            retrying = self.pending_reconnect_profile_name is not None
            message = t("status_error") + (t("status_error_retry_suffix") if retrying else "")
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip(t("tray_tooltip_error", app=APP_NAME))
            self._update_toggle_button(ERROR, message, disconnect_action=retrying, on=retrying)
        elif connected:
            message = t("status_connected", name=self.active_profile_name)
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_connected)
            self.tray.setToolTip(
                t("tray_tooltip_connected", app=APP_NAME, name=self.active_profile_name)
            )
            self._update_toggle_button(CONNECTED, message, disconnect_action=True, on=True)
        else:
            self.status_text.setText(t("status_idle"))
            self.tray.setIcon(self.icon_disconnected)
            self.tray.setToolTip(t("tray_tooltip_disconnected", app=APP_NAME))
            self._update_toggle_button(
                ACCENT, t("status_connect_tooltip"), disconnect_action=False, on=False
            )

        # Same "is there an active/in-progress session" logic as the on= flags
        # above - only the applicable one of connect/disconnect shows in the
        # tray menu at a time.
        show_disconnect = connecting or kill_switch or connected or (
            error and self.pending_reconnect_profile_name is not None
        )
        self.tray_connect_action.setVisible(not show_disconnect)
        self.tray_disconnect_action.setVisible(show_disconnect)

        if connected:
            if self._last_ip_country is not None:
                ip, country = self._last_ip_country
                self.ip_label.setText(t("ip_label", value=f"{ip} · {country}"))
        else:
            self.time_label.setText(t("time_label", value="—"))
            self.traffic_label.setText(t("traffic_label", value="—"))
            self._last_ip_country = None
            self.ip_label.setText(t("ip_label", value="—"))
            self._ip_lookup_generation += 1

    def _tick(self) -> None:
        if self.active_profile_name is None or self.connected_since is None:
            return

        elapsed = time.monotonic() - self.connected_since
        self.time_label.setText(t("time_label", value=format_duration(elapsed)))

        traffic = fetch_traffic(CLASH_API_ADDRESS, timeout=0.5)
        if traffic is not None:
            download, upload = traffic
            value = f"↓{format_bytes(download)}  ↑{format_bytes(upload)}"
            self.traffic_label.setText(t("traffic_label", value=value))
        else:
            self.traffic_label.setText(t("traffic_label", value="—"))

    def _on_singbox_exit(self, returncode: int) -> None:
        # Called (via Signal, so safely on the main thread) when sing-box dies
        # unexpectedly - i.e. neither connect_selected() nor disconnect() stopped it.
        was_real_tunnel = self.active_profile_name is not None
        crashed_profile_name = self.active_profile_name or self.pending_reconnect_profile_name
        self.active_profile_name = None
        self.connected_since = None

        if not was_real_tunnel and not self.kill_switch_active:
            # The block-all session itself died with nothing to reconnect to.
            self._set_status(connected=False)
            return

        if not crashed_profile_name:
            self.kill_switch_active = False
            self._set_status(connected=False, error=True)
            return

        self.pending_reconnect_profile_name = crashed_profile_name
        self._engage_kill_switch_if_enabled()
        self._set_status(connected=False, error=True, kill_switch=self.kill_switch_active)
        self.tray.showMessage(
            APP_NAME,
            t("tray_msg_dropped")
            + (t("tray_msg_dropped_killswitch_suffix") if self.kill_switch_active else ""),
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        delay = RECONNECT_DELAYS_MS[min(self.reconnect_attempt, len(RECONNECT_DELAYS_MS) - 1)]
        self.reconnect_attempt += 1
        self.reconnect_timer.start(delay)

    def _reconnect_tick(self) -> None:
        name = self.pending_reconnect_profile_name
        if not name:
            return
        profile = next((p for p in self.profiles if p.name == name), None)
        if profile is None:
            self.pending_reconnect_profile_name = None
            return

        if self._do_connect(profile, manual=False):
            self.tray.showMessage(
                APP_NAME, t("tray_msg_reconnected", name=profile.name),
                QSystemTrayIcon.MessageIcon.Information, 4000,
            )
        else:
            self._schedule_reconnect()

    def _check_for_updates(self) -> None:
        threading.Thread(target=self._run_update_check, daemon=True).start()

    def _run_update_check(self) -> None:
        info = updater.check_for_update(APP_VERSION)
        if info is not None:
            self.update_check_result.emit(info)

    def _show_update_available(self, info: updater.UpdateInfo) -> None:
        reply = QMessageBox.question(
            self,
            t("dlg_update_available_title"),
            t("dlg_update_available_body", version=info.version, current=APP_VERSION),
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_update_download(info)

    def _start_update_download(self, info: updater.UpdateInfo) -> None:
        self.tray.showMessage(
            APP_NAME, t("tray_msg_update_downloading"),
            QSystemTrayIcon.MessageIcon.Information, 3000,
        )
        threading.Thread(
            target=self._run_update_download, args=(info,), daemon=True
        ).start()

    def _run_update_download(self, info: updater.UpdateInfo) -> None:
        dest_path = paths.update_installer_path(info.version)
        try:
            updater.download_installer(info.download_url, dest_path)
            self.update_download_result.emit((dest_path, None))
        except updater.UpdateError as exc:
            self.update_download_result.emit((None, str(exc)))

    def _show_update_download_result(self, result: tuple) -> None:
        dest_path, error = result
        if error is not None:
            QMessageBox.warning(self, t("dlg_update_download_failed_title"), error)
            return

        subprocess.Popen([str(dest_path)])
        self._quit()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _quit(self) -> None:
        self.reconnect_timer.stop()
        self.manager.stop()
        # Unlike a regular disconnect, quitting must not race the app process
        # exiting - a daemon thread still mid-teardown gets killed outright when
        # the interpreter shuts down, abandoning the graceful sing-box stop.
        self.manager.wait_until_stopped(GRACEFUL_STOP_TIMEOUT + 2)
        QApplication.instance().quit()


def run(start_minimized: bool = False) -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(APP_STYLESHEET)
    _ico = str(paths.assets_dir() / "icon.ico")
    app.setWindowIcon(QIcon(_ico))
    window = MainWindow()
    if not start_minimized:
        window.show()
    return app.exec()
