"""Tray icon + main window: import from clipboard/QR, profile list, connect/disconnect,
kill switch, auto-reconnect, autostart, connection test, profile backup/restore."""

from __future__ import annotations

import dataclasses
import threading
import time

from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPainter, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
    QLabel,
    QHBoxLayout,
)

from . import autostart, paths, profile_store, settings
from .edit_profile_dialog import EditProfileDialog
from .json_edit_dialog import JsonEditDialog
from .qr_import import decode_qr_from_file, decode_qr_from_qimage
from .singbox_config import CLASH_API_ADDRESS
from .singbox_manager import SingBoxManager
from .split_tunnel_dialog import SplitTunnelDialog
from .stats import fetch_traffic, format_bytes, format_duration
from .profile_parser import Profile, ProfileParseError, looks_like_profile_uri, parse_profile_uri

STATUS_TICK_MS = 1000
RECONNECT_DELAYS_MS = [3000, 6000, 12000, 24000, 30000]

KEBAB_ICON_SIZE = QSize(24, 24)
PASTE_ICON_SIZE = QSize(20, 20)
SPEED_ICON_SIZE = QSize(20, 20)
QR_ICON_SIZE = QSize(20, 20)
SPLIT_TUNNEL_ICON_SIZE = QSize(20, 20)

SPEED_TEST_IDLE_TEXT = " Тест скорости"

BUTTON_STYLESHEET = """
QPushButton {
    min-height: 30px;
    padding: 4px 14px;
}
"""


def _make_icon(color: str) -> QIcon:
    # Must run after a QApplication exists - QPixmap aborts the process otherwise.
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


def _make_dot(color: str, size: int = 14) -> QPixmap:
    # Must run after a QApplication exists - QPixmap aborts the process otherwise.
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    return pixmap


def _load_svg_icon(filename: str) -> QIcon:
    icon_path = paths.assets_dir() / filename
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


class MainWindow(QMainWindow):
    # SingBoxManager's watchdog calls on_exit from a background thread; emitting a
    # signal (instead of touching widgets directly) marshals the call back onto the
    # Qt main thread via a queued connection.
    singbox_exited = Signal(int)
    connection_test_result = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VLESS Client")
        self.resize(460, 440)

        self.icon_disconnected = _make_icon("#888888")
        self.icon_connected = _make_icon("#2ecc71")
        self.icon_error = _make_icon("#e74c3c")

        self.dot_disconnected = _make_dot("#888888")
        self.dot_connected = _make_dot("#2ecc71")
        self.dot_error = _make_dot("#e74c3c")
        self.dot_killswitch = _make_dot("#e67e22")

        self.settings = settings.load_settings()

        self.manager = SingBoxManager(on_exit=self.singbox_exited.emit)
        self.singbox_exited.connect(self._on_singbox_exit)
        self.connection_test_result.connect(self._show_connection_test_result)

        self.profiles = profile_store.load_profiles()
        self.active_profile_name: str | None = None
        self.selected_profile_name: str | None = None
        self.connected_since: float | None = None
        self.kill_switch_active = False
        self.pending_reconnect_profile_name: str | None = None
        self.reconnect_attempt = 0

        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setSingleShot(True)
        self.reconnect_timer.timeout.connect(self._reconnect_tick)

        central = QWidget()
        layout = QVBoxLayout(central)

        status_row = QHBoxLayout()
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(14, 14)
        self.status_dot.setPixmap(self.dot_disconnected)
        self.status_text = QLabel("Отключено")
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        status_row.addStretch()
        layout.addLayout(status_row)

        self.time_label = QLabel("Время соединения: —")
        layout.addWidget(self.time_label)

        self.traffic_label = QLabel("Трафик: —")
        layout.addWidget(self.traffic_label)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._tick)
        self.status_timer.start(STATUS_TICK_MS)

        add_config_btn = QPushButton(" Добавить конфигурацию")
        add_config_menu = QMenu(add_config_btn)

        paste_action = add_config_menu.addAction(
            _load_svg_icon("paste_icon.svg"), "Конфигурация из буфера обмена"
        )
        paste_action.triggered.connect(self.import_from_clipboard)

        qr_action = add_config_menu.addAction(
            _load_svg_icon("qr_icon.svg"), "Конфигурация из QR"
        )
        qr_action.triggered.connect(self.import_from_qr_file)

        manual_action = add_config_menu.addAction(
            _load_svg_icon("add_icon.svg"), "Добавить вручную"
        )
        manual_action.triggered.connect(self.add_profile_manually)

        # Show the menu manually instead of QPushButton.setMenu() - setMenu() draws
        # its own dropdown-arrow indicator next to the text, which we don't want.
        add_config_btn.clicked.connect(
            lambda _checked=False, b=add_config_btn, m=add_config_menu: m.exec(
                b.mapToGlobal(b.rect().bottomLeft())
            )
        )
        layout.addWidget(add_config_btn)

        options_row = QHBoxLayout()
        self.kill_switch_checkbox = QCheckBox("Kill switch")
        self.kill_switch_checkbox.setToolTip(
            "Блокировать интернет, если туннель неожиданно обрывается"
        )
        self.kill_switch_checkbox.setChecked(self.settings.kill_switch_enabled)
        self.kill_switch_checkbox.toggled.connect(self._on_kill_switch_toggled)
        options_row.addWidget(self.kill_switch_checkbox)

        self.autostart_checkbox = QCheckBox("Автозапуск с Windows")
        try:
            self.autostart_checkbox.setChecked(autostart.is_enabled())
        except OSError:
            self.autostart_checkbox.setChecked(False)
        self.autostart_checkbox.toggled.connect(self._on_autostart_toggled)
        options_row.addWidget(self.autostart_checkbox)

        self.auto_connect_checkbox = QCheckBox("Подключаться при запуске")
        self.auto_connect_checkbox.setChecked(self.settings.auto_connect_on_launch)
        self.auto_connect_checkbox.toggled.connect(self._on_auto_connect_toggled)
        options_row.addWidget(self.auto_connect_checkbox)

        split_tunnel_btn = QPushButton(" Split tunneling")
        split_tunnel_btn.setIcon(_load_svg_icon("split_tunnel_icon.svg"))
        split_tunnel_btn.setIconSize(SPLIT_TUNNEL_ICON_SIZE)
        split_tunnel_btn.clicked.connect(self.open_split_tunnel_settings)
        options_row.addWidget(split_tunnel_btn)
        layout.addLayout(options_row)

        self.profile_list = QListWidget()
        self._row_checkboxes: dict[str, QCheckBox] = {}
        self._refresh_profile_list()
        layout.addWidget(self.profile_list)

        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.clicked.connect(self._on_connect_button_clicked)
        layout.addWidget(self.connect_btn)

        self.test_btn = QPushButton(SPEED_TEST_IDLE_TEXT)
        self.test_btn.setIcon(_load_svg_icon("speed_icon.svg"))
        self.test_btn.setIconSize(SPEED_ICON_SIZE)
        self.test_btn.clicked.connect(self.test_connection)
        layout.addWidget(self.test_btn)

        self.setCentralWidget(central)

        self.tray = QSystemTrayIcon(self.icon_disconnected, self)
        self.tray.setToolTip("VLESS Client — отключено")
        tray_menu_actions = self._build_tray_menu()
        self.tray.setContextMenu(tray_menu_actions)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        if self.settings.auto_connect_on_launch and self.settings.last_active_profile:
            profile = next(
                (p for p in self.profiles if p.name == self.settings.last_active_profile), None
            )
            if profile is not None:
                QTimer.singleShot(500, lambda: self._do_connect(profile, manual=False))

    def _build_tray_menu(self):
        menu = QMenu()
        show_action = QAction("Открыть", self)
        show_action.triggered.connect(self.showNormal)
        menu.addAction(show_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.triggered.connect(self.disconnect)
        menu.addAction(disconnect_action)

        menu.addSeparator()
        quit_action = QAction("Выход", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
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
            menu_btn.setIcon(_load_svg_icon("kebab_icon.svg"))
            menu_btn.setIconSize(KEBAB_ICON_SIZE)
            menu_btn.setFixedWidth(32)
            row_menu = QMenu(menu_btn)
            edit_json_action = row_menu.addAction("Редактировать JSON")
            edit_json_action.triggered.connect(
                lambda _checked=False, name=profile.name: self._open_json_editor(name)
            )
            edit_profile_action = row_menu.addAction("Редактировать профиль")
            edit_profile_action.triggered.connect(
                lambda _checked=False, name=profile.name: self._edit_profile(name)
            )
            delete_action = row_menu.addAction("Удалить")
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
                self,
                "Конфиг изменён",
                "Этот профиль был подключён — переподключитесь, чтобы применить изменения.",
            )
            self.disconnect()

    def import_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text and looks_like_profile_uri(text):
            self._import_text(text)
            return

        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            decoded = decode_qr_from_qimage(clipboard.image())
            if decoded:
                self._import_text(decoded)
                return

        QMessageBox.warning(
            self,
            "Импорт не удался",
            "В буфере обмена нет vless-ссылки и не найден QR-код с подключением",
        )

    def import_from_qr_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать изображение с QR-кодом", "", "Изображения (*.png *.jpg *.jpeg *.bmp)"
        )
        if not path:
            return

        decoded = decode_qr_from_file(path)
        if not decoded:
            QMessageBox.warning(self, "QR не распознан", "Не удалось найти QR-код на изображении")
            return
        self._import_text(decoded)

    def _import_text(self, text: str) -> None:
        try:
            profile = parse_profile_uri(text)
        except ProfileParseError as exc:
            QMessageBox.warning(self, "Импорт не удался", str(exc))
            return

        self.profiles = profile_store.add_profile(profile)
        self._refresh_profile_list()
        QMessageBox.information(
            self, "Профиль импортирован", f"Добавлен профиль: {profile.name}"
        )

    def _selected_profile(self):
        if not self.selected_profile_name:
            return None
        for profile in self.profiles:
            if profile.name == self.selected_profile_name:
                return profile
        return None

    def _on_connect_button_clicked(self) -> None:
        if self.connect_btn.text() == "Отключиться":
            self.disconnect()
        else:
            self.connect_selected()

    def connect_selected(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            QMessageBox.warning(self, "Нет профиля", "Выберите профиль из списка")
            return

        self.reconnect_timer.stop()
        self.reconnect_attempt = 0
        self._do_connect(profile, manual=True)

    def _do_connect(self, profile: Profile, manual: bool) -> bool:
        if self.manager.is_running:
            self.manager.stop()

        try:
            self.manager.start(profile, excluded_processes=self.settings.excluded_processes)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            if manual:
                QMessageBox.critical(self, "Не удалось подключиться", str(exc))
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
        self.tray.showMessage(
            "VLESS Client", f"Подключено: {profile.name}",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )
        return True

    def _engage_kill_switch_if_enabled(self) -> None:
        if not self.settings.kill_switch_enabled:
            self.kill_switch_active = False
            return
        try:
            self.manager.start_blockall()
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
            QMessageBox.warning(self, "Не удалось сохранить", str(exc))
            return

        if self.selected_profile_name == profile.name:
            self.selected_profile_name = updated.name
        self._refresh_profile_list()

        if was_active:
            QMessageBox.information(
                self,
                "Профиль изменён",
                "Этот профиль был подключён — переподключитесь, чтобы применить изменения.",
            )
            self.disconnect()

    def _delete_profile(self, profile_name: str) -> None:
        profile = next((p for p in self.profiles if p.name == profile_name), None)
        if profile is None:
            return

        confirm = QMessageBox.question(
            self,
            "Удалить профиль",
            f"Удалить профиль «{profile.name}»?",
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
        blank_profile = Profile(name="Новый профиль")
        dialog = EditProfileDialog(blank_profile, self)
        dialog.setWindowTitle("Добавить профиль")
        if dialog.exec() != EditProfileDialog.DialogCode.Accepted:
            return

        new_profile = dialog.result_profile
        if new_profile is None:
            return

        if any(p.name == new_profile.name for p in self.profiles):
            QMessageBox.warning(
                self,
                "Профиль уже существует",
                f"Профиль с именем «{new_profile.name}» уже есть. Переименуйте и попробуйте снова.",
            )
            return

        self.profiles = profile_store.add_profile(new_profile)
        self._refresh_profile_list()
        QMessageBox.information(self, "Профиль добавлен", f"Добавлен профиль: {new_profile.name}")

    def test_connection(self) -> None:
        if self.active_profile_name is None:
            QMessageBox.information(self, "Не подключено", "Сначала подключитесь к серверу")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(SPEED_TEST_IDLE_TEXT + "...")
        threading.Thread(target=self._run_connection_test, daemon=True).start()

    def _run_connection_test(self) -> None:
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

    def _show_connection_test_result(self, result: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText(SPEED_TEST_IDLE_TEXT)

        if result.startswith("OK:"):
            _, ping_ms, download_mbps, upload_mbps = result.split(":")
            QMessageBox.information(
                self,
                "Результат теста скорости",
                f"Пинг: {ping_ms} мс\nСкачивание: {download_mbps} Мбит/с\nЗагрузка: {upload_mbps} Мбит/с",
            )
        else:
            QMessageBox.warning(
                self, "Тест скорости не удался", f"Ошибка: {result[5:]}"
            )

    def open_split_tunnel_settings(self) -> None:
        dialog = SplitTunnelDialog(self.settings.excluded_processes, self)
        if dialog.exec() != SplitTunnelDialog.DialogCode.Accepted:
            return
        self.settings.excluded_processes = dialog.result_processes()
        settings.save_settings(self.settings)
        if self.active_profile_name is not None:
            QMessageBox.information(
                self,
                "Split tunneling изменён",
                "Чтобы применить новый список, переподключитесь.",
            )

    def _on_kill_switch_toggled(self, checked: bool) -> None:
        self.settings.kill_switch_enabled = checked
        settings.save_settings(self.settings)

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
            QMessageBox.warning(self, "Автозапуск", str(exc))
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not checked)
            self.autostart_checkbox.blockSignals(False)

    def _set_status(self, connected: bool, error: bool = False, kill_switch: bool = False) -> None:
        if kill_switch:
            self.status_dot.setPixmap(self.dot_killswitch)
            self.status_text.setText("Заблокировано (kill switch) — переподключение...")
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip("VLESS Client — kill switch")
            self.connect_btn.setText("Отключиться")
            self.connect_btn.setEnabled(True)
        elif error:
            retrying = self.pending_reconnect_profile_name is not None
            self.status_dot.setPixmap(self.dot_error)
            self.status_text.setText(
                "Ошибка подключения" + (", переподключение..." if retrying else "")
            )
            self.tray.setIcon(self.icon_error)
            self.tray.setToolTip("VLESS Client — ошибка")
            self.connect_btn.setText("Отключиться" if retrying else "Подключиться")
            self.connect_btn.setEnabled(True)
        elif connected:
            self.status_dot.setPixmap(self.dot_connected)
            self.status_text.setText(f"Подключено ({self.active_profile_name})")
            self.tray.setIcon(self.icon_connected)
            self.tray.setToolTip(f"VLESS Client — подключено: {self.active_profile_name}")
            self.connect_btn.setText("Отключиться")
            self.connect_btn.setEnabled(True)
        else:
            self.status_dot.setPixmap(self.dot_disconnected)
            self.status_text.setText("Отключено")
            self.tray.setIcon(self.icon_disconnected)
            self.tray.setToolTip("VLESS Client — отключено")
            self.connect_btn.setText("Подключиться")
            self.connect_btn.setEnabled(True)

        if not connected:
            self.time_label.setText("Время соединения: —")
            self.traffic_label.setText("Трафик: —")

    def _tick(self) -> None:
        if self.active_profile_name is None or self.connected_since is None:
            return

        elapsed = time.monotonic() - self.connected_since
        self.time_label.setText(f"Время соединения: {format_duration(elapsed)}")

        traffic = fetch_traffic(CLASH_API_ADDRESS, timeout=0.5)
        if traffic is not None:
            download, upload = traffic
            self.traffic_label.setText(
                f"Трафик: ↓{format_bytes(download)}  ↑{format_bytes(upload)}"
            )
        else:
            self.traffic_label.setText("Трафик: —")

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
            "VLESS Client",
            "Соединение разорвано"
            + (" — интернет заблокирован (kill switch)" if self.kill_switch_active else ""),
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
                "VLESS Client", f"Переподключено: {profile.name}",
                QSystemTrayIcon.MessageIcon.Information, 4000,
            )
        else:
            self._schedule_reconnect()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _quit(self) -> None:
        self.reconnect_timer.stop()
        self.manager.stop()
        QApplication.instance().quit()


def run(start_minimized: bool = False) -> int:
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(BUTTON_STYLESHEET)
    window = MainWindow()
    if not start_minimized:
        window.show()
    return app.exec()
