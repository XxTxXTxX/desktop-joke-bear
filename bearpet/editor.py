"""提醒编辑器分发：Windows 用原生 EDIT + GDI，macOS 用 NSTextField。

两个后端暴露同一个 ReminderEditor 类与同一套方法（open/close/destroy/commit/alive）。
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from .editor_win import *  # noqa: F401,F403
else:
    from .editor_mac import *  # noqa: F401,F403
