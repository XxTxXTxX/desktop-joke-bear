"""自嘲熊桌面宠物 —— 启动入口。

    python main.py        正常启动（带控制台）
    pythonw main.py       无控制台启动
"""
from __future__ import annotations

import ctypes
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# 本地依赖目录（pip install --target .deps pillow）
DEPS = os.path.join(BASE, ".deps")
if os.path.isdir(DEPS) and DEPS not in sys.path:
    sys.path.insert(0, DEPS)
if BASE not in sys.path:
    sys.path.insert(0, BASE)

_instance_handle = None
PID_PATH = os.path.join(BASE, ".bear.pid")


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
    """同名互斥体，防止一口气养出好几只熊。"""
    global _instance_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.CreateMutexW(None, False, "Global\\DeskBearPet_singleton")
    if not handle:
        return True
    if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
        return False
    _instance_handle = handle
    return True


def main() -> int:
    if not _single_instance():
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
        pet.run()
    except KeyboardInterrupt:
        pet.shutdown()
    finally:
        _clear_pid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
