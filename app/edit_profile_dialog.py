"""Dialog for editing a profile's connection parameters: every field is exposed
and editable, with irrelevant fields hidden depending on the selected protocol."""

from __future__ import annotations

import dataclasses

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
)

from .i18n import t
from .profile_parser import Profile

PROTOCOL_OPTIONS = ["vless", "shadowsocks", "trojan", "hysteria2", "tuic"]
SECURITY_OPTIONS = ["none", "tls", "reality"]
NETWORK_OPTIONS = ["tcp", "ws", "grpc", "http"]
FINGERPRINT_OPTIONS = [
    "",
    "chrome",
    "firefox",
    "safari",
    "ios",
    "android",
    "edge",
    "360",
    "qq",
    "random",
]
METHOD_OPTIONS = [
    "aes-256-gcm",
    "aes-128-gcm",
    "chacha20-ietf-poly1305",
    "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305",
]
OBFS_OPTIONS = ["", "salamander"]
CONGESTION_CONTROL_OPTIONS = ["bbr", "cubic", "new_reno"]

# Which rows are relevant for each protocol. Rows not listed for a protocol are
# hidden via QFormLayout.setRowVisible() when that protocol is selected.
FIELDS_BY_PROTOCOL = {
    "vless": {
        "uuid", "security", "network", "flow", "sni", "fingerprint",
        "public_key", "short_id", "spider_x", "alpn", "path", "host_header", "service_name",
    },
    "shadowsocks": {"method", "password"},
    "trojan": {
        "password", "security", "network", "sni", "fingerprint",
        "alpn", "path", "host_header", "service_name",
    },
    "hysteria2": {"password", "sni", "alpn", "obfs", "obfs_password", "insecure"},
    "tuic": {"uuid", "password", "sni", "alpn", "congestion_control", "insecure"},
}


class EditProfileDialog(QDialog):
    def __init__(self, profile: Profile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("edit_profile_title", name=profile.name))
        self.setMinimumWidth(620)
        self.original_profile = profile

        layout = QFormLayout(self)
        self._field_rows: dict[str, object] = {}

        self.name_edit = QLineEdit(profile.name)
        layout.addRow(t("form_label_name"), self.name_edit)

        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(PROTOCOL_OPTIONS)
        self.protocol_combo.setCurrentText(profile.protocol)
        self.protocol_combo.currentTextChanged.connect(self._update_field_visibility)
        layout.addRow(t("form_label_protocol"), self.protocol_combo)

        self.host_edit = QLineEdit(profile.host)
        layout.addRow(t("form_label_host"), self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(profile.port)
        layout.addRow(t("form_label_port"), self.port_spin)

        self.uuid_edit = QLineEdit(profile.uuid)
        self._add_row(layout, "uuid", "UUID", self.uuid_edit)

        self.password_edit = QLineEdit(profile.password)
        self._add_row(layout, "password", "Password", self.password_edit)

        self.method_combo = QComboBox()
        self.method_combo.addItems(METHOD_OPTIONS)
        self.method_combo.setEditable(True)
        if profile.method and profile.method not in METHOD_OPTIONS:
            self.method_combo.addItem(profile.method)
        self.method_combo.setCurrentText(profile.method or METHOD_OPTIONS[0])
        self._add_row(layout, "method", "Method (cipher)", self.method_combo)

        self.security_combo = QComboBox()
        self.security_combo.addItems(SECURITY_OPTIONS)
        self.security_combo.setCurrentText(profile.security)
        self._add_row(layout, "security", "Security", self.security_combo)

        self.network_combo = QComboBox()
        self.network_combo.addItems(NETWORK_OPTIONS)
        self.network_combo.setCurrentText(profile.network)
        self._add_row(layout, "network", "Network (type)", self.network_combo)

        self.flow_edit = QLineEdit(profile.flow)
        self._add_row(layout, "flow", "Flow", self.flow_edit)

        self.sni_edit = QLineEdit(profile.sni)
        self._add_row(layout, "sni", "SNI", self.sni_edit)

        self.fingerprint_combo = QComboBox()
        self.fingerprint_combo.addItems(FINGERPRINT_OPTIONS)
        self.fingerprint_combo.setEditable(True)  # allow a custom value if the server needs one
        if profile.fingerprint and profile.fingerprint not in FINGERPRINT_OPTIONS:
            self.fingerprint_combo.addItem(profile.fingerprint)
        self.fingerprint_combo.setCurrentText(profile.fingerprint)
        self._add_row(layout, "fingerprint", "Fingerprint (fp)", self.fingerprint_combo)

        self.public_key_edit = QLineEdit(profile.public_key)
        self._add_row(layout, "public_key", "Reality public key (pbk)", self.public_key_edit)

        self.short_id_edit = QLineEdit(profile.short_id)
        self._add_row(layout, "short_id", "Reality short id (sid)", self.short_id_edit)

        self.spider_x_edit = QLineEdit(profile.spider_x)
        self._add_row(layout, "spider_x", "Reality spiderX (spx)", self.spider_x_edit)

        self.alpn_edit = QLineEdit(",".join(profile.alpn))
        self._add_row(layout, "alpn", t("form_label_alpn"), self.alpn_edit)

        self.path_edit = QLineEdit(profile.path)
        self._add_row(layout, "path", "Path (ws/http)", self.path_edit)

        self.host_header_edit = QLineEdit(profile.host_header)
        self._add_row(layout, "host_header", "Host header (ws/http)", self.host_header_edit)

        self.service_name_edit = QLineEdit(profile.service_name)
        self._add_row(layout, "service_name", "Service name (grpc)", self.service_name_edit)

        self.obfs_combo = QComboBox()
        self.obfs_combo.addItems(OBFS_OPTIONS)
        self.obfs_combo.setCurrentText(profile.obfs)
        self._add_row(layout, "obfs", "Obfs", self.obfs_combo)

        self.obfs_password_edit = QLineEdit(profile.obfs_password)
        self._add_row(layout, "obfs_password", "Obfs password", self.obfs_password_edit)

        self.insecure_checkbox = QCheckBox(t("checkbox_insecure"))
        self.insecure_checkbox.setChecked(profile.insecure)
        self._add_row(layout, "insecure", "", self.insecure_checkbox)

        self.congestion_control_combo = QComboBox()
        self.congestion_control_combo.addItems(CONGESTION_CONTROL_OPTIONS)
        self.congestion_control_combo.setCurrentText(profile.congestion_control)
        self._add_row(layout, "congestion_control", "Congestion control", self.congestion_control_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.result_profile: Profile | None = None
        self._update_field_visibility(self.protocol_combo.currentText())

    def _add_row(self, layout: QFormLayout, key: str, label: str, widget) -> None:
        layout.addRow(label, widget)
        self._field_rows[key] = widget

    def _update_field_visibility(self, protocol: str) -> None:
        relevant = FIELDS_BY_PROTOCOL.get(protocol, set())
        layout: QFormLayout = self.layout()
        for key, widget in self._field_rows.items():
            layout.setRowVisible(widget, key in relevant)

    def _on_save(self) -> None:
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        protocol = self.protocol_combo.currentText()
        uuid = self.uuid_edit.text().strip()
        password = self.password_edit.text().strip()
        method = self.method_combo.currentText().strip()

        if not name or not host:
            QMessageBox.warning(self, t("dlg_fill_fields_title"), t("dlg_fill_fields_body"))
            return

        if protocol in ("vless", "tuic") and not uuid:
            QMessageBox.warning(self, t("dlg_missing_data_title"), t("dlg_missing_uuid"))
            return
        if protocol in ("shadowsocks", "trojan", "hysteria2", "tuic") and not password:
            QMessageBox.warning(self, t("dlg_missing_data_title"), t("dlg_missing_password"))
            return
        if protocol == "shadowsocks" and not method:
            QMessageBox.warning(self, t("dlg_missing_data_title"), t("dlg_missing_method"))
            return

        alpn = [a.strip() for a in self.alpn_edit.text().split(",") if a.strip()]

        profile = dataclasses.replace(
            self.original_profile,
            name=name,
            protocol=protocol,
            host=host,
            port=self.port_spin.value(),
            uuid=uuid,
            password=password,
            method=method,
            security=self.security_combo.currentText(),
            network=self.network_combo.currentText(),
            flow=self.flow_edit.text().strip(),
            sni=self.sni_edit.text().strip(),
            fingerprint=self.fingerprint_combo.currentText().strip(),
            public_key=self.public_key_edit.text().strip(),
            short_id=self.short_id_edit.text().strip(),
            spider_x=self.spider_x_edit.text().strip(),
            alpn=alpn,
            path=self.path_edit.text().strip(),
            host_header=self.host_header_edit.text().strip(),
            service_name=self.service_name_edit.text().strip(),
            obfs=self.obfs_combo.currentText(),
            obfs_password=self.obfs_password_edit.text().strip(),
            insecure=self.insecure_checkbox.isChecked(),
            congestion_control=self.congestion_control_combo.currentText(),
        )

        if profile.protocol == "vless" and profile.security == "reality" and not profile.public_key:
            QMessageBox.warning(
                self, t("dlg_missing_data_title"), t("dlg_missing_pbk")
            )
            return

        self.result_profile = profile
        self.accept()
