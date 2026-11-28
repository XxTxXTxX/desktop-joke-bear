"""Win32 分层窗口封装 —— 纯 ctypes，无第三方依赖。

关键点：
  * WS_EX_LAYERED + UpdateLayeredWindow(ULW_ALPHA) → 真正的逐像素 alpha，
    熊的轮廓外不会被抠出彩色边，也不需要 chroma-key。
  * 透明像素天然穿透鼠标：桌面图标照样能点。
  * WS_EX_TOOLWINDOW：不占任务栏、不进 Alt+Tab。
  * WS_EX_NOACTIVATE：点熊不会抢走当前窗口的焦点。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

# ---- 常量 -----------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

HWND_TOPMOST = -1
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0
BI_RGB = 0

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
WM_SETCURSOR = 0x0020
CS_DBLCLKS = 0x0008
PM_REMOVE = 0x0001
IDC_HAND = 32649
IDC_ARROW = 32512
VK_LBUTTON = 0x01
SW_HIDE = 0
SW_SHOWNA = 8

MONITOR_DEFAULTTONEAREST = 2


def set_on_exit(cb):
    pass


MIN_Y = None


def ground_bottom():
    return work_area(None)[3]


# ---- 结构体 ---------------------------------------------------------
class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND), ("message", wt.UINT), ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM), ("time", wt.DWORD), ("pt", wt.POINT),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", wt.BYTE), ("BlendFlags", wt.BYTE),
                ("SourceConstantAlpha", wt.BYTE), ("AlphaFormat", wt.BYTE)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


# ---- 原型 -----------------------------------------------------------
user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterClassExW.restype = wt.ATOM
user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID,
]
user32.PeekMessageW.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [
    wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
    wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD,
    ctypes.POINTER(BLENDFUNCTION), wt.DWORD,
]
user32.SetWindowPos.restype = wt.BOOL
user32.SetWindowPos.argtypes = [
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT,
]
user32.SetCapture.restype = wt.HWND
user32.SetCapture.argtypes = [wt.HWND]
user32.ReleaseCapture.restype = wt.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.MonitorFromWindow.restype = wt.HANDLE
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.GetMonitorInfoW.restype = wt.BOOL
user32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.POINTER(MONITORINFO)]
user32.LoadCursorW.restype = wt.HANDLE
user32.LoadCursorW.argtypes = [wt.HINSTANCE, wt.LPCWSTR]
user32.SetCursor.restype = wt.HANDLE
user32.SetCursor.argtypes = [wt.HANDLE]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.DestroyWindow.argtypes = [wt.HWND]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.GetForegroundWindow.restype = wt.HWND
user32.GetForegroundWindow.argtypes = []
user32.IsWindow.restype = wt.BOOL
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.IsIconic.argtypes = [wt.HWND]
user32.IsZoomed.restype = wt.BOOL
user32.IsZoomed.argtypes = [wt.HWND]
user32.GetWindowRect.restype = wt.BOOL
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
kernel32.GetCurrentProcessId.restype = wt.DWORD
kernel32.GetCurrentProcessId.argtypes = []

try:
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wt.HWND, wt.DWORD, wt.LPVOID, wt.DWORD,
    ]
except Exception:
    dwmapi = None
DWMWA_EXTENDED_FRAME_BOUNDS = 9

gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
    ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD,
]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]


def cursor_pos() -> tuple[int, int]:
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def left_button_down() -> bool:
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)


def work_area(hwnd: int) -> tuple[int, int, int, int]:
    """返回窗口所在显示器的可用工作区 (left, top, right, bottom)。"""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if hmon and user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, 1920, 1040


_SKIP_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "MultitaskingViewFrame", "ForegroundStaging",
    "NotifyIconOverflowWindow",
}


def window_bounds(hwnd: int) -> tuple[int, int, int, int] | None:
    """获取指定窗口的可见外框 (left, top, right, bottom)；若窗口已关闭或最小化返回 None。"""
    if not hwnd or not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    r = wt.RECT()
    if dwmapi is not None:
        hr = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)
        )
        if hr == 0 and r.right > r.left and r.bottom > r.top:
            return r.left, r.top, r.right, r.bottom
    if user32.GetWindowRect(hwnd, ctypes.byref(r)) and r.right > r.left and r.bottom > r.top:
        return r.left, r.top, r.right, r.bottom
    return None


def foreground_window_ledge(bear_hwnd: int | None = None) -> tuple[int, int, int, int, int] | None:
    """若当前前台窗口是普通窗口化（非全屏、非最大化）窗口，返回 (hwnd, left, top, right, bottom)。"""
    fg = user32.GetForegroundWindow()
    if not fg or fg == bear_hwnd:
        return None
    if not user32.IsWindowVisible(fg) or user32.IsIconic(fg) or user32.IsZoomed(fg):
        return None
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    if pid.value == kernel32.GetCurrentProcessId():
        return None
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, buf, 64)
    cls = buf.value
    if cls in _SKIP_CLASSES or cls.startswith("BearLayeredWnd_"):
        return None
    rect = window_bounds(fg)
    if rect is None:
        return None
    l, t, r, b = rect
    w_left, w_top, w_right, w_bottom = work_area(bear_hwnd or fg)
    work_w = max(1, w_right - w_left)
    work_h = max(1, w_bottom - w_top)
    width = r - l
    height = b - t
    # 排除最大化/近全屏窗口，以及太窄、顶边太靠上或太贴地的窗口
    if width >= work_w - 28 and height >= work_h - 28:
        return None
    if width < 220 or height < 120:
        return None
    if t < w_top + 110 or t > w_bottom - 90:
        return None
    cl = max(l, w_left)
    cr = min(r, w_right)
    if cr - cl < 180:
        return None
    return int(fg), cl, t, cr, b


class LayeredWindow:
    """一块逐像素透明的独立窗口，内容由 PIL 图像逐帧推送。"""

    _class_seq = 0

    def __init__(self, width: int, height: int, title: str = "bearpet",
                 click_handlers: bool = True, auto_show: bool = True):
        self.width = width
        self.height = height
        self.x = -10000
        self.y = -10000
        self.alive = True
        self._shown = False
        # 主窗口第一次 blit 就该显示；弹层（菜单/面板）自己调 show()
        self._want_visible = bool(auto_show)
        self._dib_w = 0
        self._dib_h = 0
        self._bits = ctypes.c_void_p()
        self._hdib = None
        self._memdc = None
        self._old_bmp = None
        self._screen_dc = None

        # 回调
        self.on_left_down = None      # (sx, sy) -> None
        self.on_left_up = None        # (sx, sy) -> None
        self.on_move = None           # (sx, sy) -> None
        self.on_right_up = None       # (sx, sy) -> None
        self.on_double_click = None   # (sx, sy) -> None

        LayeredWindow._class_seq += 1
        self._cls_name = f"BearLayeredWnd_{LayeredWindow._class_seq}"
        hinst = kernel32.GetModuleHandleW(None)

        self._wndproc_ref = WNDPROC(self._wndproc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = CS_DBLCLKS
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.cast(IDC_HAND, wt.LPCWSTR))
        wc.lpszClassName = self._cls_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(err)

        ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        if not click_handlers:
            ex |= WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
        else:
            ex |= WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            ex, self._cls_name, title, WS_POPUP,
            self.x, self.y, width, height, None, None, hinst, None,
        )
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

    # ---- 消息 ------------------------------------------------------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_DESTROY:
                self.alive = False
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_ERASEBKGND or msg == WM_PAINT:
                return 1
            if msg == WM_NCHITTEST:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            if msg == WM_SETCURSOR:
                cur = user32.LoadCursorW(None, ctypes.cast(IDC_HAND, wt.LPCWSTR))
                user32.SetCursor(cur)
                return 1
            if msg == WM_LBUTTONDOWN:
                user32.SetCapture(hwnd)
                if self.on_left_down:
                    self.on_left_down(*cursor_pos())
                return 0
            if msg == WM_LBUTTONUP:
                user32.ReleaseCapture()
                if self.on_left_up:
                    self.on_left_up(*cursor_pos())
                return 0
            if msg == WM_LBUTTONDBLCLK:
                if self.on_double_click:
                    self.on_double_click(*cursor_pos())
                return 0
            if msg == WM_RBUTTONUP:
                if self.on_right_up:
                    self.on_right_up(*cursor_pos())
                return 0
            if msg == WM_MOUSEMOVE:
                if self.on_move:
                    self.on_move(*cursor_pos())
                return 0
        except Exception:  # 回调异常绝不能让消息循环炸掉
            import traceback
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def pump(self) -> bool:
        """处理排队消息；收到 WM_QUIT 返回 False。"""
        msg = MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
            if msg.message == WM_QUIT:
                self.alive = False
                return False
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return True

    # ---- 绘制 ------------------------------------------------------
    def _ensure_dib(self, w: int, h: int):
        if self._dib_w == w and self._dib_h == h:
            return
        self._free_dib()
        self._screen_dc = user32.GetDC(None)
        self._memdc = gdi32.CreateCompatibleDC(self._screen_dc)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        self._hdib = gdi32.CreateDIBSection(
            self._memdc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
        )
        if not self._hdib:
            raise ctypes.WinError(ctypes.get_last_error())
        self._bits = bits
        self._old_bmp = gdi32.SelectObject(self._memdc, self._hdib)
        self._dib_w, self._dib_h = w, h

    def _free_dib(self):
        if self._memdc and self._old_bmp:
            gdi32.SelectObject(self._memdc, self._old_bmp)
            self._old_bmp = None
        if self._hdib:
            gdi32.DeleteObject(self._hdib)
            self._hdib = None
        if self._memdc:
            gdi32.DeleteDC(self._memdc)
            self._memdc = None
        if self._screen_dc:
            user32.ReleaseDC(None, self._screen_dc)
            self._screen_dc = None
        self._dib_w = self._dib_h = 0

    def blit(self, img, x: int | None = None, y: int | None = None):
        """把 RGBA 图像推到屏幕上（位置可直接更新，等于移动+重绘）。"""
        w, h = img.size
        self._ensure_dib(w, h)
        data = img.tobytes("raw", "BGRA")
        ctypes.memmove(self._bits, data, len(data))
        if x is not None:
            self.x = int(x)
        if y is not None:
            self.y = int(y)
        pos = wt.POINT(self.x, self.y)
        size = wt.SIZE(w, h)
        src = wt.POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        if not user32.UpdateLayeredWindow(
            self.hwnd, self._screen_dc, ctypes.byref(pos), ctypes.byref(size),
            self._memdc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if self._want_visible and not self._shown:
            # WS_POPUP 默认不可见；UpdateLayeredWindow 只负责内容与位置。
            # 只有"调用方明确要求显示"时才自动 ShowWindow —— 否则 hide() 之后
            # 任何一次 blit（比如面板自己重绘）都会把它重新弹出来。
            user32.ShowWindow(self.hwnd, SW_SHOWNA)
            user32.SetWindowPos(self.hwnd, HWND_TOPMOST, self.x, self.y, 0, 0,
                                SWP_NOSIZE | SWP_NOACTIVATE)
            self._shown = True

    def move(self, x: int, y: int):
        self.x, self.y = int(x), int(y)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, self.x, self.y, 0, 0,
                            SWP_NOSIZE | SWP_NOACTIVATE)

    def raise_topmost(self):
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def show(self):
        user32.ShowWindow(self.hwnd, SW_SHOWNA)
        self._shown = True
        self._want_visible = True

    def hide(self):
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self._shown = False
        self._want_visible = False

    @property
    def visible(self) -> bool:
        return self._shown and self._want_visible

    def work_area(self):
        return work_area(self.hwnd)

    def destroy(self):
        self._free_dib()
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self.alive = False
