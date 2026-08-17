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
    QPointF,
    QRect,
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
    QRadialGradient,
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
APP_VERSION = "1.3.0"

STATUS_TICK_MS = 1000
RECONNECT_DELAYS_MS = [3000, 6000, 12000, 24000, 30000]

KEBAB_ICON_SIZE = QSize(24, 24)
PASTE_ICON_SIZE = QSize(20, 20)
SPEED_ICON_SIZE = QSize(20, 20)
QR_ICON_SIZE = QSize(20, 20)
SPLIT_TUNNEL_ICON_SIZE = QSize(20, 20)


def _speed_test_idle_text() -> str:
    return f" {t('speed_test_idle')}"

SIDEBAR_WIDTH = 190
POWER_BTN_SIZE = 140
LOG_EXPORT_TAIL_BYTES = 2 * 1024 * 1024

# Palette - "Graphite": monochrome silver pulled from the logo, so app chrome and
# icon read as one product. Color is reserved almost entirely for connection-state
# signaling (connecting/connected/error) - everything else stays grayscale.
BG_APP = "#0C0C0E"
BG_SIDEBAR = "#141416"
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
#sidebar {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
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

NAV_BUTTON_STYLESHEET = f"""
QPushButton {{
    text-align: left;
    padding: 10px 12px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QPushButton:hover {{
    background: {BG_CARD_ALT};
    color: {TEXT_PRIMARY};
}}
QPushButton:checked {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    font-weight: 600;
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


_HOME_ICON_TEMPLATE = (paths.assets_dir() / "home_icon.svg").read_text(encoding="utf-8")


def _draw_home_icon(color: str, size: int = 18, dpr: float = 1.0) -> QPixmap:
    svg_data = _HOME_ICON_TEMPLATE.replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap, painter = _new_supersampled_painter(size)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return _finish_supersampled(pixmap, size, dpr)


_SERVERS_ICON_TEMPLATE = (paths.assets_dir() / "servers_icon.svg").read_text(encoding="utf-8")


def _draw_servers_icon(color: str, size: int = 18, dpr: float = 1.0) -> QPixmap:
    svg_data = _SERVERS_ICON_TEMPLATE.replace("{color}", color)
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


_POWER_ICON_TEMPLATE = (paths.assets_dir() / "power_icon.svg").read_text(encoding="utf-8")


def _draw_power_icon(color: str, size: int = 56, dpr: float = 1.0) -> QPixmap:
    svg_data = _POWER_ICON_TEMPLATE.replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap, painter = _new_supersampled_painter(size)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return _finish_supersampled(pixmap, size, dpr)


HOVER_GROW = 0.05  # max size increase on hover, as a fraction of the button's size


class PowerButton(QPushButton):
    """Circular connect/disconnect button: soft embossed radial-gradient disc with a
    faint state-colored glow ring, rather than a flat fill with a hard colored border.
    Grows slightly and glows brighter on hover."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state_color = QColor(ACCENT)
        self._disc_pixmap: QPixmap | None = None
        self._hover_progress = 0.0
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_anim_value)
        self._glow_effect = QGraphicsDropShadowEffect(self)
        self._glow_effect.setOffset(0, 0)
        self._glow_effect.setBlurRadius(0)
        self.setGraphicsEffect(self._glow_effect)
        self.setFlat(True)
        # The app-level QPushButton rule sets `min-height`, which - once this widget
        # is polished (e.g. on show()) - overrides a plain setFixedSize() for the
        # height only (width is untouched since no `min-width` is set globally).
        # Pin all four bounds here, on the widget's own stylesheet, to win that fight.
        self.setStyleSheet(
            f"QPushButton {{"
            f"    border: none;"
            f"    background: transparent;"
            f"    padding: 0px;"
            f"    min-width: {POWER_BTN_SIZE}px;"
            f"    max-width: {POWER_BTN_SIZE}px;"
            f"    min-height: {POWER_BTN_SIZE}px;"
            f"    max-height: {POWER_BTN_SIZE}px;"
            f"}}"
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_state(self, color: str) -> None:
        self._state_color = QColor(color)
        self._disc_pixmap = self._build_disc_pixmap(color, self.devicePixelRatioF() or 1.0)
        self._update_glow()
        self.update()

    def refresh(self) -> None:
        """Re-render at the widget's current devicePixelRatioF(). A window's real
        DPI association can settle later than construction time - most reliably
        seen on elevated (UAC) launches - so callers re-invoke this once the
        window is actually on screen instead of trusting the value read earlier."""
        self.set_state(self._state_color.name())

    def _update_glow(self) -> None:
        # Soft ambient glow via a blurred drop shadow with zero offset, rather than
        # a hard-edged ring - intensifies as the hover animation runs.
        glow_color = QColor(self._state_color)
        glow_color.setAlpha(round(220 * self._hover_progress))
        self._glow_effect.setColor(glow_color)
        self._glow_effect.setBlurRadius(28 * self._hover_progress)

    def _on_hover_anim_value(self, value) -> None:
        self._hover_progress = float(value)
        self._update_glow()
        self.update()

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

    def _build_disc_pixmap(self, color: str, dpr: float) -> QPixmap:
        """Everything the button shows - glow ring, gradient disc, icon - composed
        once into a single pre-antialiased pixmap at set_state() time,
        rather than drawn live in paintEvent(). Drawing straight onto the widget
        with QPainter(self) turned out to still come out jagged on this app's
        elevated (UAC "runas") window specifically, even with correct Per-Monitor-V2
        DPI awareness confirmed - something about how DWM composites elevated
        windows, not this process's own DPI setup. Compositing everything into a
        supersampled-then-downscaled pixmap first, and blitting only that single
        finished pixmap in paintEvent(), keeps the whole disc smooth regardless."""
        size = POWER_BTN_SIZE
        pixmap, painter = _new_supersampled_painter(size)

        center = QPointF(size / 2, size / 2)
        # Rendered slightly smaller than the widget's own bounds, leaving headroom
        # for paintEvent() to scale this pixmap up by up to HOVER_GROW on hover
        # without clipping against the widget's edge.
        radius = (size / 2) / (1 + HOVER_GROW)

        # Outer glow ring, tinted by the current state color.
        glow = QColor(color)
        glow.setAlpha(150)
        painter.setPen(QPen(glow, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius - 1.5, radius - 1.5)

        # Main disc: radial gradient for an embossed, non-flat look. Kept clearly
        # lighter than the window background so the button reads as a raised disc.
        # Sized to reach right up under the ring stroke, not leave a visible gap.
        disc_radius = radius - 2
        gradient = QRadialGradient(
            QPointF(center.x(), center.y() - disc_radius * 0.25), disc_radius * 1.15
        )
        gradient.setColorAt(0.0, QColor("#363c48"))
        gradient.setColorAt(0.55, QColor("#23272f"))
        gradient.setColorAt(1.0, QColor("#16181d"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(center, disc_radius, disc_radius)

        painter.end()
        disc = _finish_supersampled(pixmap, size, dpr)

        icon_size = round(56 / (1 + HOVER_GROW))
        icon = _draw_power_icon(color, icon_size, dpr)
        composed = QPixmap(disc)
        icon_painter = QPainter(composed)
        # Center using the known *logical* sizes, not icon.rect()/composed.rect() -
        # those report physical pixels once devicePixelRatio is set (e.g. 175 for a
        # nominal 140), which threw centering off by exactly that logical/physical gap.
        icon_rect = QRect(0, 0, icon_size, icon_size)
        icon_rect.moveCenter(QRect(0, 0, size, size).center())
        icon_painter.drawPixmap(icon_rect, icon)
        icon_painter.end()
        return composed

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._disc_pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scale = 1.0 + HOVER_GROW * self._hover_progress
        w = self.width() * scale
        h = self.height() * scale
        target = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        painter.drawPixmap(target, self._disc_pixmap, QRectF(self._disc_pixmap.rect()))
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
        self.resize(760, 560)
        self.setMinimumSize(680, 520)

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

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(central)

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

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(4)

        nav_items = [
            ("nav_home", _draw_home_icon),
            ("nav_servers", _draw_servers_icon),
            ("nav_settings", _draw_settings_icon),
        ]
        self.nav_buttons: list[QPushButton] = []
        self._nav_specs: list[tuple[QPushButton, str, object]] = []
        self._nav_icon_cache: dict[int, tuple[QIcon, QIcon]] = {}
        self._nav_group = QButtonGroup(sidebar)
        self._nav_group.setExclusive(True)
        for index, (label_key, draw_fn) in enumerate(nav_items):
            btn = QPushButton(f"  {t(label_key)}")
            btn.setCheckable(True)
            btn.setStyleSheet(NAV_BUTTON_STYLESHEET)
            btn.setIconSize(QSize(18, 18))
            btn.toggled.connect(lambda checked, b=btn: self._apply_nav_icon(b, checked))
            btn.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self._nav_group.addButton(btn)
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
            self._nav_specs.append((btn, label_key, draw_fn))

        self._refresh_nav_icons()

        layout.addStretch(1)

        self.export_logs_btn = QPushButton(f"  {t('export_logs_btn')}")
        self.export_logs_btn.setStyleSheet(NAV_BUTTON_STYLESHEET)
        self.export_logs_btn.setIcon(
            QIcon(_draw_themed_icon("logs_icon.svg", TEXT_MUTED, 18, self.devicePixelRatioF() or 1.0))
        )
        self.export_logs_btn.setIconSize(QSize(18, 18))
        self.export_logs_btn.clicked.connect(self._export_logs)
        layout.addWidget(self.export_logs_btn)
        layout.addSpacing(12)

        # One line, centered - spans the same full sidebar width as the button
        # above it, so centering here lines its middle up with the button's.
        brand_label = QLabel(
            f'<span style="font-weight:700; font-size:13px;">{APP_NAME}</span>'
            f'&nbsp;&nbsp;<span style="color:{TEXT_MUTED}; font-size:11px;">'
            f"v{APP_VERSION}</span>"
        )
        brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_label)

        return sidebar

    def _refresh_nav_icons(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        for btn, _label_key, draw_fn in self._nav_specs:
            inactive = QIcon(draw_fn(TEXT_MUTED, 18, dpr))
            active = QIcon(draw_fn(ACCENT, 18, dpr))
            self._nav_icon_cache[id(btn)] = (inactive, active)
            btn.setIcon(active if btn.isChecked() else inactive)

    def _retranslate_nav_buttons(self) -> None:
        for btn, label_key, _draw_fn in self._nav_specs:
            btn.setText(f"  {t(label_key)}")

    def _apply_nav_icon(self, btn: QPushButton, checked: bool) -> None:
        icons = self._nav_icon_cache.get(id(btn))
        if icons is not None:
            btn.setIcon(icons[1] if checked else icons[0])

    def _refresh_dpi_dependent_icons(self) -> None:
        """Re-render our own hand-drawn icons (nav icons, the power button disc)
        at the window's actual devicePixelRatioF(). Called once from showEvent()
        and once more shortly after on a timer, because on this app that value
        was observed to sometimes only settle to its correct scaled value a
        moment after the window is first shown - most reliably reproduced when
        launched elevated (UAC "runas")."""
        self._refresh_nav_icons()
        self.connect_btn.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._refresh_dpi_dependent_icons()
        QTimer.singleShot(400, self._refresh_dpi_dependent_icons)

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_home_page())
        self.pages.addWidget(self._build_servers_page())
        self.pages.addWidget(self._build_settings_page())
        layout.addWidget(self.pages, 1)

        return content

    def _build_add_menu_button(self) -> QPushButton:
        btn = QPushButton(f" {t('btn_add')}")
        # Deliberately not the plain global QPushButton style - this and the main
        # connect button are the app's two primary calls-to-action, so both wear a
        # permanent accent border rather than picking one up only on hover.
        btn.setStyleSheet(
            f"QPushButton {{"
            f"    background-color: {BG_CARD};"
            f"    border: 1.5px solid {ACCENT};"
            f"    border-radius: 8px;"
            f"    padding: 8px 14px;"
            f"    min-height: 18px;"
            f"}}"
            f"QPushButton:hover {{"
            f"    background-color: {BG_CARD_ALT};"
            f"    border-color: {ACCENT_HOVER};"
            f"}}"
            f"QPushButton:pressed {{"
            f"    background-color: {BG_CARD};"
            f"}}"
        )
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

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addStretch(1)

        self.connect_btn = PowerButton()
        self.connect_btn.setFixedSize(POWER_BTN_SIZE, POWER_BTN_SIZE)
        self.connect_btn.clicked.connect(self._on_connect_button_clicked)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.connect_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addSpacing(18)

        self.status_text = QLabel(t("status_idle"))
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_text)

        # Fixed height and always visible (even with empty text) so the connect
        # button doesn't jump up/down as these rows fill in or clear - a hidden
        # widget is excluded from layout entirely, which was shifting the stretch
        # above the button every time connection state changed.
        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.time_label.setFixedHeight(18)
        layout.addWidget(self.time_label)

        self.traffic_label = QLabel()
        self.traffic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.traffic_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.traffic_label.setFixedHeight(18)
        layout.addWidget(self.traffic_label)

        self.ip_label = QLabel()
        self.ip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ip_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        self.ip_label.setFixedHeight(18)
        layout.addWidget(self.ip_label)

        layout.addStretch(2)

        add_btn = self._build_add_menu_button()
        add_btn.setFixedWidth(220)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        bottom_row.addWidget(add_btn)
        bottom_row.addStretch(1)

        layout.addLayout(bottom_row)
        return page

    def _build_servers_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        self.servers_title_label = QLabel(t("servers_title"))
        self.servers_title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_row.addWidget(self.servers_title_label)
        header_row.addStretch(1)
        add_btn = self._build_add_menu_button()
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        self.profile_list = QListWidget()
        self._row_checkboxes: dict[str, QCheckBox] = {}
        layout.addWidget(self.profile_list, 1)

        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.settings_title_label = QLabel(t("settings_title"))
        self.settings_title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(self.settings_title_label)

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

        self.split_tunnel_btn = QPushButton(f" {t('split_tunnel_btn')}")
        self.split_tunnel_btn.setIcon(
            QIcon(_draw_themed_icon("split_tunnel_icon.svg", TEXT_MUTED, 20, dpr))
        )
        self.split_tunnel_btn.setIconSize(SPLIT_TUNNEL_ICON_SIZE)
        self.split_tunnel_btn.clicked.connect(self.open_split_tunnel_settings)
        layout.addWidget(self.split_tunnel_btn)

        self.test_btn = QPushButton(_speed_test_idle_text())
        self.test_btn.setIcon(QIcon(_draw_themed_icon("speed_icon.svg", TEXT_MUTED, 20, dpr)))
        self.test_btn.setIconSize(SPEED_ICON_SIZE)
        self.test_btn.clicked.connect(self.test_connection)
        layout.addWidget(self.test_btn)

        layout.addStretch(1)
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
        self._retranslate_nav_buttons()
        self.servers_title_label.setText(t("servers_title"))
        self.settings_title_label.setText(t("settings_title"))
        self.language_row_label.setText(t("language_label"))
        self.kill_switch_checkbox.setText(t("kill_switch_label"))
        self._update_kill_switch_hint()
        self.autostart_checkbox.setText(t("autostart_label"))
        self.auto_connect_checkbox.setText(t("auto_connect_label"))
        self.split_tunnel_btn.setText(f" {t('split_tunnel_btn')}")
        self.export_logs_btn.setText(f"  {t('export_logs_btn')}")

        # Mid-test the button shows idle-text + "..."; anything else (enabled) is idle.
        was_testing = not self.test_btn.isEnabled()
        self.test_btn.setText(_speed_test_idle_text() + ("..." if was_testing else ""))

        for btn in self._add_menu_buttons:
            btn.setText(f" {t('btn_add')}")
        for action, key in self._add_menu_action_specs:
            action.setText(t(key))

        self.tray_show_action.setText(t("tray_open"))
        self.tray_disconnect_action.setText(t("tray_disconnect"))
        self.tray_quit_action.setText(t("tray_quit"))

        # Status text/tooltips/tray tooltip all depend on current connection state.
        self._set_status(*self._last_status_args)

    def _show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def _build_tray_menu(self):
        menu = QMenu()
        self.tray_show_action = QAction(t("tray_open"), self)
        self.tray_show_action.triggered.connect(self.showNormal)
        menu.addAction(self.tray_show_action)

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
        self.kill_switch_checkbox.setToolTip(text)
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

    def _update_power_button(self, color: str, tooltip: str, disconnect_action: bool) -> None:
        self._connect_action_is_disconnect = disconnect_action
        self.connect_btn.setToolTip(tooltip)
        self.connect_btn.set_state(color)

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
            self._update_power_button(CONNECTING, message, disconnect_action=False)
        elif kill_switch:
            message = t("status_killswitch")
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip(t("tray_tooltip_killswitch", app=APP_NAME))
            self._update_power_button(WARNING, message, disconnect_action=True)
        elif error:
            retrying = self.pending_reconnect_profile_name is not None
            message = t("status_error") + (t("status_error_retry_suffix") if retrying else "")
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip(t("tray_tooltip_error", app=APP_NAME))
            self._update_power_button(ERROR, message, disconnect_action=retrying)
        elif connected:
            message = t("status_connected", name=self.active_profile_name)
            self.status_text.setText(message)
            self.tray.setIcon(self.icon_connected)
            self.tray.setToolTip(
                t("tray_tooltip_connected", app=APP_NAME, name=self.active_profile_name)
            )
            self._update_power_button(CONNECTED, message, disconnect_action=True)
        else:
            self.status_text.setText(t("status_idle"))
            self.tray.setIcon(self.icon_disconnected)
            self.tray.setToolTip(t("tray_tooltip_disconnected", app=APP_NAME))
            self._update_power_button(
                ACCENT, t("status_connect_tooltip"), disconnect_action=False
            )

        if connected:
            if self._last_ip_country is not None:
                ip, country = self._last_ip_country
                self.ip_label.setText(t("ip_label", value=f"{ip} · {country}"))
        else:
            self.time_label.setText("")
            self.traffic_label.setText("")
            self._last_ip_country = None
            self.ip_label.setText("")
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
