"""自嘲熊通用启动器 —— Windows / macOS 共用同一个文件。

    python 启动自嘲熊.py        （或 python3 启动自嘲熊.py）

自动检查并补齐项目内 .deps 依赖，随后无控制台/脱离终端启动 main.py。
"""
from __future__ import annotations

import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DEPS = os.path.join(BASE, ".deps")
MAIN = os.path.join(BASE, "main.py")


def _has(module: str) -> bool:
    if DEPS not in sys.path:
        sys.path.insert(0, DEPS)
    try:
        __import__(module)
        return True
    except Exception:
        return False


def ensure_deps() -> None:
    packages = ["pillow"]
    modules = ["PIL"]
    if sys.platform == "darwin":
        packages.append("pyobjc-framework-cocoa")
        modules.append("AppKit")
    missing = [p for p, m in zip(packages, modules) if not _has(m)]
    if not missing:
        return
    print("正在安装项目依赖：" + " ".join(missing))
    try:
        subprocess.run([sys.executable, "-m", "pip", "install",
                        "--target", DEPS, *missing], check=True)
    except Exception as exc:
        print(f"依赖安装失败：{exc}")
        print(f"请手动运行: pip install --target .deps {' '.join(missing)}")


def pythonw() -> str:
    exe = sys.executable
    if sys.platform == "win32":
        candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(candidate):
            return candidate
    return exe


def launch() -> None:
    ensure_deps()
    if sys.platform == "win32":
        subprocess.Popen([pythonw(), MAIN], cwd=BASE,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen([pythonw(), MAIN], cwd=BASE, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("自嘲熊已启动。")


if __name__ == "__main__":
    launch()
