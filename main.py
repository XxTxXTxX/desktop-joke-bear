from __future__ import annotations

import ctypes
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

DEPS = os.path.join(BASE, ".deps")
if os.path.isdir(DEPS) and DEPS not in sys.path:
    sys.path.insert(0, DEPS)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_instance_handle = None
try:
    from bearpet.paths import data_dir as _data_dir
    DATA_DIR = _data_dir()
except Exception:
    DATA_DIR = BASE
PID_PATH = os.path.join(DATA_DIR, ".bear.pid")


def _write_pid():
    try:
        with open(PID_PATH, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _clear_pid():
    try:
        os.remove(PID_PATH)
    except OSError:
        pass


def _single_instance() -> bool:
    """单实例锁：Windows 用命名互斥体，macOS/Linux 用 flock 锁文件。"""
    global _instance_handle
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, "Global\\DeskBearPet_singleton")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
            return False
        _instance_handle = handle
        return True

    import fcntl

    try:
        lock = open(os.path.join(DATA_DIR, ".bear.lock"), "w", encoding="ascii")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    _instance_handle = lock
    return True


def _activate_existing() -> None:
    """已经有实例在跑时，把它的熊窗口提到最前，而不是静默退出。"""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.restype = ctypes.c_void_p
        hwnd = user32.FindWindowW("BearLayeredWnd_1", None)
        if not hwnd:
            return
        user32.ShowWindow(hwnd, 5)  # SW_SHOW
        # HWND_TOPMOST + SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def main() -> int:
    if not _single_instance():
        _activate_existing()
        return 0
    try:
        from bearpet.app import BearPet
    except ImportError as exc:
        print("缺少依赖，请先运行: pip install --target .deps pillow")
        print(f"  详细: {exc}")
        return 1
    pet = BearPet()
    _write_pid()
    try:
        from bearpet import winlayer as _winlayer
        _winlayer.set_on_exit(_clear_pid)
    except Exception:
        pass
    try:
        pet.run()
    except KeyboardInterrupt:
        pet.shutdown()
    finally:
        _clear_pid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
