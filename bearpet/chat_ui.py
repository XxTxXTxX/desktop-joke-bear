"""聊天窗口分发：Windows / macOS 共用 ChatWindow API。"""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from .chat_ui_win import *  # noqa: F401,F403
else:
    from .chat_ui_mac import *  # noqa: F401,F403
