"""desktop-bear —— 自嘲熊桌面宠物。

模块划分：
    lines.py     台词库
    art.py       程序化矢量绘制（无素材依赖，逐帧生成）
    winlayer.py  Win32 分层窗口封装（ctypes，逐像素 alpha）
    brain.py     行为状态机
    app.py       主循环 / 物理 / 交互
"""

__version__ = "1.0.0"
