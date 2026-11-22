"""添加提醒的小窗口：普通 Win32 弹出窗 + 标准 EDIT 控件。

不用分层窗口的原因：`UpdateLayeredWindow` 不合成子控件，而中文输入必须靠真正的
EDIT 控件（自带 IME、光标、选区、粘贴）。所以这里用普通窗口：背景、按钮、色块
全部用 GDI 画，只有"打字"交给系统。

交互：Enter = 添加，Esc = 取消，拖标题区域可移动。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as wt

from . import winlayer as W

user32 = W.user32
gdi32 = W.gdi32

# ---------------------------------------------------------------- 常量
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_TOPMOST = 0x00000008
ES_AUTOHSCROLL = 0x0080

WM_SETFONT = 0x0030
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_SETTEXT = 0x000C
WM_KEYDOWN = 0x0100
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
GWLP_WNDPROC = -4

DT_CENTER = 0x0001
DT_LEFT = 0x0000
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_NOPREFIX = 0x0800
HTCAPTION = 2
SW_SHOW = 5
SW_HIDE = 0
TRANSPARENT = 1

CW, CH = 392, 300
COL_BG = 0x00F6F2EC          # BGR
COL_INK = 0x001A0C08
COL_DIM = 0x006A5A4A
COL_LINE = 0x00C2CFD9
COL_ON_BG = 0x00C9E9FF
COL_ON_INK = 0x000C5A8A
COL_PRIMARY = 0x00057ECE
FONT_NAME = "Microsoft YaHei"

# ---------------------------------------------------------------- 版式
MSG_BOX = (16, 38, CW - 16, 68)
QUICK_Y = 78
TIME_LABEL_Y = 106
TIME_Y = 124
CUSTOM_LABEL_Y = 156
CUSTOM_EDIT = (104, 152, 96, 26)
REP_LABEL_Y = 192
REP_Y = 210
BTN_Y = 252

QUICK = [("喝水", "记得喝水"), ("走走", "起来走走活动一下"), ("吃饭", "该吃饭了"),
         ("早睡", "早点睡，别熬夜"), ("夸她", "你很好看，今天也是")]
TIMES = [("现在", ""), ("10分钟", "in:10m"), ("1小时", "in:1h"), ("20:00", "20:00")]
REPEATS = [("不重复", ""), ("每天", "daily"), ("工作日", "weekday")]


# ---------------------------------------------------------------- 结构体/原型
class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT),
                ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
                ("rgbReserved", wt.BYTE * 32)]


gdi32.RoundRect.argtypes = [wt.HDC] + [ctypes.c_int] * 6
gdi32.CreateSolidBrush.restype = wt.HBRUSH
gdi32.CreateSolidBrush.argtypes = [wt.COLORREF]
gdi32.CreatePen.restype = wt.HPEN
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.COLORREF]
gdi32.CreateFontW.restype = wt.HFONT
# 14 个参数：高 宽 角度 方向 粗细 + 8 个样式位 + 字体名
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.SetTextColor.argtypes = [wt.HDC, wt.COLORREF]
gdi32.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
user32.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HBRUSH]
user32.DrawTextW.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int,
                             ctypes.POINTER(wt.RECT), wt.UINT]
user32.BeginPaint.restype = wt.HDC
user32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.UpdateWindow.argtypes = [wt.HWND]
user32.SetFocus.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.MessageBeep.argtypes = [wt.UINT]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [wt.HWND, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]


def _chips(items, y, x0=16, h=26, gap=8):
    """从左到右排一组小按钮，返回 [(rect, label, value)]。"""
    out, x = [], x0
    for label, value in items:
        wide = any(ord(c) > 127 for c in label)
        w = 22 + len(label) * 14 if wide else 18 + len(label) * 8
        out.append(((x, y, x + w, y + h), label, value))
        x += w + gap
    return out


class ReminderEditor:
    def __init__(self, pet):
        self.pet = pet
        self.alive = False
        self.quick = _chips(QUICK, QUICK_Y, h=24, gap=6)
        self.times = _chips(TIMES, TIME_Y)
        self.reps = _chips(REPEATS, REP_Y)
        self.btn_ok = (CW - 112, BTN_Y, CW - 16, BTN_Y + 34)
        self.btn_cancel = (CW - 202, BTN_Y, CW - 122, BTN_Y + 34)
        self.sel_time, self.sel_rep = 1, 0
        self._old_edit_proc = None
        self._edit_ref = None
        self._proc_ref = None
        self._wc = None
        self.hwnd = self.edit_msg = self.edit_time = self._font = None
        self._build()

    # ------------------------------------------------------------ 建窗
    def _build(self):
        hinst = W.kernel32.GetModuleHandleW(None)
        cls = "BearReminderEditor"
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        self._proc_ref = W.WNDPROC(self._proc)        # 必须持有引用
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.cast(32512, wt.LPCWSTR))
        wc.lpszClassName = cls
        wc.hbrBackground = gdi32.CreateSolidBrush(COL_BG)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:
                raise ctypes.WinError(err)
        self._wc = wc

        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW, cls, "添加提醒", WS_POPUP,
            0, 0, CW, CH, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        self._font = gdi32.CreateFontW(-15, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, FONT_NAME)
        ex, ey, ex2, ey2 = MSG_BOX
        self.edit_msg = self._make_edit(ex, ey, ex2 - ex, ey2 - ey)
        self.edit_time = self._make_edit(*CUSTOM_EDIT)

        self._edit_ref = W.WNDPROC(self._edit_proc)
        self._old_edit_proc = user32.SetWindowLongPtrW(
            self.edit_msg, GWLP_WNDPROC, ctypes.cast(self._edit_ref, ctypes.c_void_p))
        user32.SetWindowLongPtrW(
            self.edit_time, GWLP_WNDPROC, ctypes.cast(self._edit_ref, ctypes.c_void_p))

    def _make_edit(self, x, y, w, h):
        hinst = W.kernel32.GetModuleHandleW(None)
        e = user32.CreateWindowExW(
            WS_EX_CLIENTEDGE, "EDIT", "",
            WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
            x, y, w, h, self.hwnd, None, hinst, None)
        user32.SendMessageW(e, WM_SETFONT, int(self._font or 0), 1)
        return e

    def _edit_proc(self, hwnd, msg, wp, lp):
        if msg == WM_KEYDOWN:
            if wp == VK_RETURN:
                self.commit()
                return 0
            if wp == VK_ESCAPE:
                self.close()
                return 0
        return user32.CallWindowProcW(self._old_edit_proc, hwnd, msg, wp, lp)

    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == W.WM_PAINT:
                self._paint(hwnd)
                return 0
            if msg == W.WM_ERASEBKGND:
                return 1
            if msg == W.WM_CLOSE:
                self.close()
                return 0
            if msg == W.WM_LBUTTONDOWN:
                x = ctypes.c_short(lp & 0xFFFF).value
                y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                self._click(x, y)
                return 0
            if msg == W.WM_NCHITTEST:
                y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                if y < 32:
                    return HTCAPTION
        except Exception:
            import traceback
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    # ------------------------------------------------------------ 绘制
    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            bg = gdi32.CreateSolidBrush(COL_BG)
            user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, CW, CH)), bg)
            gdi32.DeleteObject(bg)
            gdi32.SelectObject(hdc, self._font)
            gdi32.SetBkMode(hdc, TRANSPARENT)

            def text(x, y, w, h, s, color=COL_INK, align=DT_CENTER):
                gdi32.SetTextColor(hdc, color)
                r = wt.RECT(x, y, x + w, y + h)
                user32.DrawTextW(hdc, s, len(s), ctypes.byref(r),
                                 align | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)

            text(16, 8, 200, 24, "添加提醒", COL_DIM, DT_LEFT)
            text(200, 8, 176, 24, "Enter 添加 / Esc 取消", 0x009A8A7A, DT_LEFT)

            def chips(items, sel):
                for i, (r, label, _v) in enumerate(items):
                    x0, y0, x1, y1 = r
                    on = (i == sel) if sel is not None else False
                    pen = gdi32.CreatePen(0, 2, 0x00081233 if on else COL_LINE)
                    oldp = gdi32.SelectObject(hdc, pen)
                    brush = gdi32.CreateSolidBrush(COL_ON_BG if on else 0x00F8FBFD)
                    oldb = gdi32.SelectObject(hdc, brush)
                    gdi32.RoundRect(hdc, x0, y0, x1, y1, 10, 10)
                    gdi32.SelectObject(hdc, oldp)
                    gdi32.SelectObject(hdc, oldb)
                    gdi32.DeleteObject(pen)
                    gdi32.DeleteObject(brush)
                    text(x0, y0, x1 - x0, y1 - y0, label, COL_ON_INK if on else COL_INK)

            chips(self.quick, None)
            text(16, TIME_LABEL_Y - 2, 120, 20, "什么时候", COL_DIM, DT_LEFT)
            chips(self.times, self.sel_time)
            text(16, CUSTOM_LABEL_Y, 84, 22, "或填 HH:MM", COL_DIM, DT_LEFT)
            text(16, REP_LABEL_Y - 2, 120, 20, "重复", COL_DIM, DT_LEFT)
            chips(self.reps, self.sel_rep)

            for rect, label, primary in ((self.btn_cancel, "取消", False),
                                         (self.btn_ok, "添加", True)):
                x0, y0, x1, y1 = rect
                pen = gdi32.CreatePen(0, 2, 0x00081233)
                oldp = gdi32.SelectObject(hdc, pen)
                brush = gdi32.CreateSolidBrush(COL_PRIMARY if primary else 0x00F8FBFD)
                oldb = gdi32.SelectObject(hdc, brush)
                gdi32.RoundRect(hdc, x0, y0, x1, y1, 12, 12)
                gdi32.SelectObject(hdc, oldp)
                gdi32.SelectObject(hdc, oldb)
                gdi32.DeleteObject(pen)
                gdi32.DeleteObject(brush)
                text(x0, y0, x1 - x0, y1 - y0, label,
                     0x00FFFFFF if primary else COL_INK)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    # ------------------------------------------------------------ 交互
    def _hit(self, x, y):
        for group, kind in ((self.quick, "quick"), (self.times, "time"), (self.reps, "rep")):
            for i, (r, _l, _v) in enumerate(group):
                if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                    return kind, i
        if self.btn_ok[0] <= x <= self.btn_ok[2] and self.btn_ok[1] <= y <= self.btn_ok[3]:
            return "ok", 0
        if self.btn_cancel[0] <= x <= self.btn_cancel[2] and self.btn_cancel[1] <= y <= self.btn_cancel[3]:
            return "cancel", 0
        return None

    def _click(self, x, y):
        hit = self._hit(x, y)
        if hit is None:
            return
        kind, idx = hit
        if kind == "quick":
            self._set_text(self.edit_msg, self.quick[idx][2])
            user32.SetFocus(self.edit_msg)
        elif kind == "time":
            self.sel_time = idx
            self._set_text(self.edit_time, "")
            self._repaint()
        elif kind == "rep":
            self.sel_rep = idx
            self._repaint()
        elif kind == "ok":
            self.commit()
        elif kind == "cancel":
            self.close()

    def _repaint(self):
        user32.InvalidateRect(self.hwnd, None, True)
        user32.UpdateWindow(self.hwnd)

    def _set_text(self, edit, s):
        buf = ctypes.create_unicode_buffer(s)      # 保持引用直到调用返回
        user32.SendMessageW(edit, WM_SETTEXT, 0, ctypes.cast(buf, ctypes.c_void_p).value)

    def _get(self, edit) -> str:
        n = int(user32.SendMessageW(edit, WM_GETTEXTLENGTH, 0, 0))
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.SendMessageW(edit, WM_GETTEXT, n + 1, ctypes.cast(buf, ctypes.c_void_p).value)
        return buf.value.strip()

    # ------------------------------------------------------------ 提交
    def commit(self):
        text = self._get(self.edit_msg)
        if not text:
            user32.MessageBeep(0)
            user32.SetFocus(self.edit_msg)
            return
        custom = self._get(self.edit_time)
        when = custom if custom else self.times[self.sel_time][2]
        repeat = self.reps[self.sel_rep][2] or None
        now = time.time()
        due = self.pet.store.resolve(now, when, repeat, False)
        if due <= now + 1:
            due = now + 5
        self.pet.store.add(text, due, repeat, source="local")
        nice = time.strftime("%m-%d %H:%M", time.localtime(due))
        self.pet.brain.say(f"记下了：{nice} {text}", 3.4)
        if self.pet.remind_panel is not None:
            self.pet.remind_panel.refresh()
        self.close()

    # ------------------------------------------------------------ 显示
    def open(self, near_x: float, near_y: float):
        left, top, right, bottom = W.work_area(self.pet.win.hwnd)
        x = int(max(left + 8, min(right - CW - 8, near_x)))
        y = int(max(top + 8, min(bottom - CH - 8, near_y)))
        self._set_text(self.edit_msg, "")
        self._set_text(self.edit_time, "")
        self.sel_time, self.sel_rep = 1, 0
        user32.SetWindowPos(self.hwnd, W.HWND_TOPMOST, x, y, CW, CH, 0x0040)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.edit_msg)
        self.alive = True
        self._repaint()

    def close(self):
        self.alive = False
        self.pet.editor_open = False
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def destroy(self):
        try:
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        except Exception:
            pass
