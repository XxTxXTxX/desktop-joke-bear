"""运行期可写目录：Windows 保持项目根目录，macOS 放到 Application Support。"""
from __future__ import annotations

import os
import sys


def data_dir() -> str:
    if sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", "自嘲熊")
    elif getattr(sys, "frozen", False) and os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(root, "自嘲熊")
    else:
        path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path
