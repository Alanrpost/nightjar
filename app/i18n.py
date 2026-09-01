"""Minimal i18n: a flat string-key -> {ru, en} dict, plus set_language()/
get_language()/t() that read a module-level "current language".

No widget auto-retranslation machinery here - dialogs and menus are built fresh
each time they're opened, so they pick up the current language automatically the
next time they're shown. MainWindow's persistent chrome (page titles,
checkboxes, tray menu, ...) is retranslated explicitly via
MainWindow.retranslate_ui() when the language setting changes."""

from __future__ import annotations

LANGUAGES = ("ru", "en")

_current_language = "ru"

_STRINGS: dict[str, dict[str, str]] = {
    # --- header ---
    "nav_settings": {"ru": "Настройки", "en": "Settings"},

    # --- home page ---
    "status_idle": {"ru": "Отключено", "en": "Disconnected"},
    "status_connect_tooltip": {"ru": "Подключиться", "en": "Connect"},
    "time_label": {"ru": "Время: {value}", "en": "Time: {value}"},
    "traffic_label": {"ru": "Трафик: {value}", "en": "Traffic: {value}"},
    "btn_add": {"ru": "Добавить", "en": "Add"},
    "ip_label": {"ru": "IP: {value}", "en": "IP: {value}"},

    # --- add-config menu ---
    "menu_import_clipboard": {
        "ru": "Конфигурация из буфера обмена", "en": "Config from clipboard",
    },
    "menu_import_qr": {"ru": "Конфигурация из QR", "en": "Config from QR code"},
    "menu_import_manual": {"ru": "Добавить вручную", "en": "Add manually"},

    # --- servers page ---
    "kebab_edit_json": {"ru": "Редактировать JSON", "en": "Edit JSON"},
    "kebab_edit_profile": {"ru": "Редактировать профиль", "en": "Edit profile"},
    "kebab_delete": {"ru": "Удалить", "en": "Delete"},

    # --- settings page ---
    "settings_title": {"ru": "Настройки", "en": "Settings"},
    "language_label": {"ru": "Язык", "en": "Language"},
    "kill_switch_label": {
        "ru": "Экстренное отключение (Kill switch)", "en": "Kill switch",
    },
    "kill_switch_hint": {
        "ru": "Если туннель неожиданно обрывается, полностью блокирует доступ в "
        "интернет до восстановления соединения — чтобы трафик не пошёл "
        "напрямую, в открытую, с настоящим IP-адресом.",
        "en": "If the tunnel drops unexpectedly, this blocks internet access "
        "entirely until the connection is restored - so traffic doesn't leak "
        "out in the open with your real IP address.",
    },
    "kill_switch_hint_include": {
        "ru": "Если туннель неожиданно обрывается, блокирует доступ в интернет "
        "только для приложений и сайтов из списка «Раздельное туннелирование» "
        "— остальной трафик и так шёл напрямую, ему нечего защищать.",
        "en": "If the tunnel drops unexpectedly, this blocks internet access "
        "only for the apps and sites in the \"Split tunneling\" list - "
        "everything else was already going direct, so there's nothing for it "
        "to fail safe on.",
    },
    "autostart_label": {"ru": "Автозапуск с Windows", "en": "Start with Windows"},
    "auto_connect_label": {"ru": "Подключаться при запуске", "en": "Connect on launch"},
    "split_tunnel_btn": {"ru": "Раздельное туннелирование", "en": "Split tunneling"},
    "speed_test_idle": {"ru": "Тест скорости", "en": "Speed test"},
    "export_logs_btn": {"ru": "Скачать логи", "en": "Download logs"},
    "dlg_no_logs_title": {"ru": "Логов пока нет", "en": "No logs yet"},
    "dlg_no_logs_body": {
        "ru": "Файл логов появится после первого подключения.",
        "en": "The log file will appear after the first connection attempt.",
    },
    "dlg_logs_saved_title": {"ru": "Логи сохранены", "en": "Logs saved"},
    "dlg_logs_saved_body": {"ru": "Сохранено в: {path}", "en": "Saved to: {path}"},
    "dlg_logs_save_failed_title": {"ru": "Не удалось сохранить логи", "en": "Failed to save logs"},
    "file_dialog_logs_filter": {
        "ru": "Файлы логов (*.log);;Все файлы (*.*)",
        "en": "Log files (*.log);;All files (*.*)",
    },

    # --- tray menu / tooltip ---
    "tray_open": {"ru": "Открыть", "en": "Open"},
    "tray_connect": {"ru": "Подключиться", "en": "Connect"},
    "tray_disconnect": {"ru": "Отключиться", "en": "Disconnect"},
    "tray_quit": {"ru": "Выход", "en": "Exit"},
    "tray_tooltip_disconnected": {
        "ru": "{app} — отключено", "en": "{app} — disconnected",
    },
    "tray_tooltip_error": {"ru": "{app} — ошибка", "en": "{app} — error"},
    "tray_tooltip_killswitch": {
        "ru": "{app} — kill switch", "en": "{app} — kill switch",
    },
    "tray_tooltip_connected": {
        "ru": "{app} — подключено: {name}",
        "en": "{app} — connected: {name}",
    },
    "tray_tooltip_connecting": {"ru": "{app} — подключение...", "en": "{app} — connecting..."},
    "tray_msg_connected": {"ru": "Подключено: {name}", "en": "Connected: {name}"},
    "tray_msg_reconnected": {"ru": "Переподключено: {name}", "en": "Reconnected: {name}"},
    "tray_msg_dropped": {"ru": "Соединение разорвано", "en": "Connection dropped"},
    "tray_msg_dropped_killswitch_suffix": {
        "ru": " — интернет заблокирован (kill switch)",
        "en": " — internet blocked (kill switch)",
    },

    # --- status text (connect button state) ---
    "status_connecting": {"ru": "Подключение...", "en": "Connecting..."},
    "status_killswitch": {
        "ru": "Заблокировано (kill switch) — переподключение...",
        "en": "Blocked (kill switch) — reconnecting...",
    },
    "status_error": {"ru": "Ошибка подключения", "en": "Connection error"},
    "status_error_retry_suffix": {
        "ru": ", переподключение...", "en": ", reconnecting...",
    },
    "status_connected": {"ru": "Подключено ({name})", "en": "Connected ({name})"},

    # --- dialogs / message boxes (home + servers pages) ---
    "dlg_config_changed_title": {"ru": "Конфиг изменён", "en": "Config changed"},
    "dlg_reconnect_to_apply": {
        "ru": "Этот профиль был подключён — переподключитесь, чтобы применить изменения.",
        "en": "This profile was connected - reconnect to apply the changes.",
    },
    "dlg_import_failed_title": {"ru": "Импорт не удался", "en": "Import failed"},
    "dlg_import_failed_body": {
        "ru": "В буфере обмена нет ссылки на конфигурацию или подписку, и не "
        "найден QR-код с подключением",
        "en": "No connection or subscription link in the clipboard, and no QR "
        "code with a connection was found",
    },
    "tray_msg_subscription_importing": {
        "ru": "Импорт подписки...", "en": "Importing subscription...",
    },
    "dlg_subscription_imported_body": {
        "ru": "Импортировано профилей: {count}", "en": "Imported {count} profile(s)",
    },
    "btn_refresh_subscriptions": {"ru": "Обновить", "en": "Refresh"},
    "dlg_no_subscriptions_title": {"ru": "Нет подписок", "en": "No subscriptions"},
    "dlg_no_subscriptions_body": {
        "ru": "Пока нет ни одного профиля, добавленного по ссылке на подписку.",
        "en": "No profile has been added from a subscription link yet.",
    },
    "dlg_subscriptions_refreshed_body": {
        "ru": "Подписки обновлены, профилей: {count}",
        "en": "Subscriptions refreshed, {count} profile(s)",
    },
    "file_dialog_qr_title": {
        "ru": "Выбрать изображение с QR-кодом", "en": "Select a QR code image",
    },
    "file_dialog_images_filter": {
        "ru": "Изображения (*.png *.jpg *.jpeg *.bmp)",
        "en": "Images (*.png *.jpg *.jpeg *.bmp)",
    },
    "dlg_qr_not_recognized_title": {"ru": "QR не распознан", "en": "QR not recognized"},
    "dlg_qr_not_recognized_body": {
        "ru": "Не удалось найти QR-код на изображении", "en": "No QR code found in the image",
    },
    "dlg_profile_imported_title": {"ru": "Профиль импортирован", "en": "Profile imported"},
    "dlg_profile_added_body": {"ru": "Добавлен профиль: {name}", "en": "Added profile: {name}"},
    "dlg_no_profile_title": {"ru": "Нет профиля", "en": "No profile"},
    "dlg_no_profile_body": {
        "ru": "Выберите профиль из списка", "en": "Select a profile from the list",
    },
    "dlg_connect_failed_title": {"ru": "Не удалось подключиться", "en": "Failed to connect"},
    "dlg_save_failed_title": {"ru": "Не удалось сохранить", "en": "Failed to save"},
    "dlg_profile_changed_title": {"ru": "Профиль изменён", "en": "Profile changed"},
    "dlg_delete_profile_title": {"ru": "Удалить профиль", "en": "Delete profile"},
    "dlg_delete_profile_body": {
        "ru": "Удалить профиль «{name}»?", "en": 'Delete profile "{name}"?',
    },
    "default_new_profile_name": {"ru": "Новый профиль", "en": "New profile"},
    "dlg_add_profile_title": {"ru": "Добавить профиль", "en": "Add profile"},
    "dlg_profile_exists_title": {
        "ru": "Профиль уже существует", "en": "Profile already exists",
    },
    "dlg_profile_exists_body": {
        "ru": "Профиль с именем «{name}» уже есть. Переименуйте и попробуйте снова.",
        "en": 'A profile named "{name}" already exists. Rename it and try again.',
    },
    "dlg_profile_added_title": {"ru": "Профиль добавлен", "en": "Profile added"},
    "dlg_not_connected_title": {"ru": "Не подключено", "en": "Not connected"},
    "dlg_not_connected_body": {
        "ru": "Сначала подключитесь к серверу", "en": "Connect to a server first",
    },
    "dlg_speed_result_title": {
        "ru": "Результат теста скорости", "en": "Speed test result",
    },
    "dlg_speed_result_body": {
        "ru": "Пинг: {ping} мс\nСкачивание: {download} Мбит/с\nЗагрузка: {upload} Мбит/с",
        "en": "Ping: {ping} ms\nDownload: {download} Mbps\nUpload: {upload} Mbps",
    },
    "dlg_speed_failed_title": {"ru": "Тест скорости не удался", "en": "Speed test failed"},
    "dlg_speed_failed_body": {"ru": "Ошибка: {error}", "en": "Error: {error}"},
    "dlg_split_tunnel_changed_title": {
        "ru": "Split tunneling изменён", "en": "Split tunneling changed",
    },
    "dlg_split_tunnel_changed_body": {
        "ru": "Чтобы применить новый список, переподключитесь.",
        "en": "Reconnect to apply the new list.",
    },
    "dlg_autostart_error_title": {"ru": "Автозапуск", "en": "Autostart"},
    "autostart_create_failed": {
        "ru": "Не удалось создать задачу автозапуска: {error}",
        "en": "Failed to create the autostart task: {error}",
    },

    # --- edit_profile_dialog.py ---
    "edit_profile_title": {"ru": "Редактировать: {name}", "en": "Edit: {name}"},
    "form_label_name": {"ru": "Имя профиля", "en": "Profile name"},
    "form_label_protocol": {"ru": "Протокол", "en": "Protocol"},
    "form_label_host": {"ru": "Сервер (host)", "en": "Server (host)"},
    "form_label_port": {"ru": "Порт", "en": "Port"},
    "form_label_alpn": {"ru": "ALPN (через запятую)", "en": "ALPN (comma-separated)"},
    "checkbox_insecure": {
        "ru": "Пропускать проверку сертификата (insecure)",
        "en": "Skip certificate verification (insecure)",
    },
    "dlg_fill_fields_title": {"ru": "Заполните поля", "en": "Fill in the fields"},
    "dlg_fill_fields_body": {
        "ru": "Имя и сервер обязательны", "en": "Name and server are required",
    },
    "dlg_missing_data_title": {"ru": "Не хватает данных", "en": "Missing data"},
    "dlg_missing_uuid": {
        "ru": "Для этого протокола нужен UUID", "en": "This protocol requires a UUID",
    },
    "dlg_missing_password": {
        "ru": "Для этого протокола нужен пароль",
        "en": "This protocol requires a password",
    },
    "dlg_missing_method": {
        "ru": "Для Shadowsocks нужен method (cipher)",
        "en": "Shadowsocks requires a method (cipher)",
    },
    "dlg_missing_pbk": {
        "ru": "Для security=reality нужен public key (pbk)",
        "en": "security=reality requires a public key (pbk)",
    },

    # --- json_edit_dialog.py ---
    "json_edit_title": {"ru": "JSON конфигурация: {name}", "en": "JSON config: {name}"},
    "json_edit_info": {
        "ru": "Это сырой конфиг sing-box, который будет передан движку при подключении.\n"
        "Если оставить пустым/сбросить - конфиг будет собран автоматически из полей профиля.",
        "en": "This is the raw sing-box config passed to the engine on connect.\n"
        "If left empty/reset, the config is built automatically from the profile's fields.",
    },
    "json_edit_reset_btn": {
        "ru": "Сбросить к автогенерации", "en": "Reset to auto-generated",
    },
    "dlg_invalid_json_title": {"ru": "Невалидный JSON", "en": "Invalid JSON"},
    "dlg_invalid_json_body": {"ru": "Ошибка разбора: {error}", "en": "Parse error: {error}"},
    "dlg_singbox_rejected_title": {
        "ru": "sing-box отклонил конфиг", "en": "sing-box rejected the config",
    },
    "dlg_singbox_rejected_body": {
        "ru": "{error}\n\nСохранить всё равно?", "en": "{error}\n\nSave anyway?",
    },
    "unknown_error": {"ru": "Неизвестная ошибка", "en": "Unknown error"},

    # --- split_tunnel_dialog.py ---
    "split_tunnel_title": {"ru": "Раздельное туннелирование", "en": "Split tunneling"},
    "split_tunnel_mode_exclude": {
        "ru": "VPN для всего, список — напрямую",
        "en": "VPN for everything, list goes direct",
    },
    "split_tunnel_mode_include": {
        "ru": "Всё напрямую, список — через VPN",
        "en": "Everything direct, list goes via VPN",
    },
    "split_tunnel_info_exclude": {
        "ru": "Приложения и сайты из списков ниже идут напрямую в обычный "
        "интернет, минуя VPN.\nПрименяется для любого активного подключения.",
        "en": "Apps and sites in the lists below go straight to the regular "
        "internet, bypassing the VPN.\nApplies to whichever connection is "
        "currently active.",
    },
    "split_tunnel_info_include": {
        "ru": "Весь остальной трафик идёт напрямую, минуя VPN. Через VPN пойдут "
        "только приложения и сайты из списков ниже.\nПрименяется для любого "
        "активного подключения.",
        "en": "All other traffic goes straight to the regular internet, bypassing "
        "the VPN. Only the apps and sites in the lists below are routed "
        "through the VPN.\nApplies to whichever connection is currently active.",
    },
    "split_tunnel_apps_label": {"ru": "Приложения (через запятую)", "en": "Apps (comma-separated)"},
    "split_tunnel_domains_label": {
        "ru": "Сайты (через запятую, например youtube.com)",
        "en": "Sites (comma-separated, e.g. youtube.com)",
    },
    "split_tunnel_pick_btn": {
        "ru": "Выбрать из процессов", "en": "Pick from running processes",
    },

    # --- process_picker_dialog.py ---
    "process_picker_title": {"ru": "Выбрать процессы", "en": "Select processes"},
    "process_picker_refresh_btn": {"ru": "Обновить", "en": "Refresh"},

    # --- updater.py ---
    "dlg_update_available_title": {"ru": "Доступно обновление", "en": "Update available"},
    "dlg_update_available_body": {
        "ru": "Доступна версия {version} (у вас {current}).\n\n"
        "Скачать и установить сейчас?",
        "en": "Version {version} is available (you have {current}).\n\n"
        "Download and install it now?",
    },
    "tray_msg_update_downloading": {
        "ru": "Скачивание обновления...", "en": "Downloading update...",
    },
    "dlg_update_download_failed_title": {
        "ru": "Не удалось скачать обновление", "en": "Failed to download the update",
    },
}


def set_language(language: str) -> None:
    global _current_language
    _current_language = language if language in LANGUAGES else "ru"


def get_language() -> str:
    return _current_language


def t(key: str, **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current_language) or entry.get("ru", key)
    return text.format(**kwargs) if kwargs else text
