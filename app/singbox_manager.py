"""Start/stop/monitor the sing-box.exe process and keep network state clean on exit."""

from __future__ import annotations

import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from . import paths
from .profile_parser import Profile
from .singbox_config import write_blockall_config_file, write_config_file

CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
GRACEFUL_STOP_TIMEOUT = 6.0


class SingBoxManager:
    """Owns a single sing-box.exe subprocess at a time."""

    def __init__(self, on_exit: Optional[Callable[[int], None]] = None) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._log_handle = None
        self._watchdog: Optional[threading.Thread] = None
        self._stop_thread: Optional[threading.Thread] = None
        self._stopping = False
        self._on_exit = on_exit

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, profile: Profile, excluded_processes: list[str] | None = None) -> None:
        config_path = write_config_file(profile, paths.app_data_dir(), excluded_processes)
        self._spawn(config_path, label=f"profile '{profile.name}'")

    def start_blockall(self) -> None:
        """Kill-switch mode: TUN stays up, but every packet is dropped."""
        config_path = write_blockall_config_file(paths.app_data_dir())
        self._spawn(config_path, label="kill-switch (block-all)")

    def _spawn(self, config_path: Path, label: str) -> None:
        if self.is_running:
            raise RuntimeError("sing-box is already running")

        # stop() returns as soon as it has signalled the old process, before that
        # process has actually released the TUN adapter (that's the whole point -
        # callers on the UI thread don't block on it). But *this* call is about to
        # ask Windows for the same adapter name again, so - unlike a plain stop()
        # - we do need the previous one fully gone first, or sing-box's "create
        # tun interface" fails immediately with "file already exists" and we come
        # up dead on arrival (the reconnect logic then quietly papers over it a
        # few seconds later). Typically resolves in well under a second.
        self.wait_until_stopped(GRACEFUL_STOP_TIMEOUT + 1)

        exe = paths.singbox_exe_path()
        if not exe.exists():
            raise FileNotFoundError(
                f"sing-box.exe not found at {exe}. See README for setup instructions."
            )

        self._log_handle = open(paths.log_file(), "a", encoding="utf-8")
        self._log_handle.write(f"\n--- starting sing-box: {label} ---\n")
        self._log_handle.flush()

        self._stopping = False
        self._process = subprocess.Popen(
            [str(exe), "run", "-c", str(config_path)],
            cwd=str(exe.parent),
            stdout=self._log_handle,
            stderr=self._log_handle,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
        paths.pid_file().write_text(str(self._process.pid), encoding="utf-8")

        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()

    def _watch(self) -> None:
        proc = self._process
        if proc is None:
            return
        returncode = proc.wait()
        if self._log_handle:
            self._log_handle.write(f"--- sing-box exited with code {returncode} ---\n")
            self._log_handle.flush()
        self._clear_pid_file()
        if not self._stopping and self._on_exit:
            self._on_exit(returncode)

    def stop(self) -> None:
        """Signal sing-box to shut down and return immediately - the actual wait
        (it can take a few seconds to gracefully tear down the TUN adapter) runs
        on a background thread so callers on the UI thread don't block/freeze.
        Use wait_until_stopped() where the caller must not proceed until it's
        really gone (e.g. before the app process itself exits)."""
        if not self.is_running:
            self._clear_pid_file()
            return

        self._stopping = True
        proc = self._process
        self._process = None
        assert proc is not None

        self._stop_thread = threading.Thread(target=self._terminate, args=(proc,), daemon=True)
        self._stop_thread.start()

    def wait_until_stopped(self, timeout: Optional[float] = None) -> None:
        stop_thread = self._stop_thread
        if stop_thread is not None:
            stop_thread.join(timeout)

    def _terminate(self, proc: subprocess.Popen) -> None:
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.wait(timeout=GRACEFUL_STOP_TIMEOUT)
        except (subprocess.TimeoutExpired, ValueError, OSError):
            proc.kill()
            try:
                proc.wait(timeout=GRACEFUL_STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass

        self._clear_pid_file()
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def _clear_pid_file(self) -> None:
        try:
            paths.pid_file().unlink(missing_ok=True)
        except OSError:
            pass
