"""窗口后端分发：Windows 用分层窗口，macOS 用 AppKit 透明窗口。

两个后端暴露完全相同的公开 API，业务模块（app / 各面板 / 菜单）无需关心平台。

公开 API：
    LayeredWindow, cursor_pos, left_button_down, work_area, HWND_TOPMOST
"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from .winlayer_win import *  # noqa: F401,F403
else:
    from .maclayer import *  # noqa: F401,F403
