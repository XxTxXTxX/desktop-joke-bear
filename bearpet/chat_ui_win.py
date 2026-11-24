"""聊天窗口（Windows）：原生 EDIT + GDI 绘制，含首次配置页。"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from . import chat as chatmod, winlayer as W

user32 = W.user32
gdi32 = W.gdi32

WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_EX_CLIENTEDGE = 0x00000200
ES_AUTOHSCROLL = 0x0080
WM_SETFONT = 0x0030
WM_KEYDOWN = 0x0100
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
GWLP_WNDPROC = -4
DT_LEFT = 0x0000
DT_CENTER = 0x0001
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_NOPREFIX = 0x0800
HTCAPTION = 2
SW_SHOW = 5
SW_HIDE = 0
TRANSPARENT = 1

CW, CH = 400, 460
INPUT_Y = CH - 52
FONT_NAME = "Microsoft YaHei"
COL_BG = 0x00F6F2EC
COL_INK = 0x001A0C08
COL_DIM = 0x006A5A4A
COL_ME = 0x00057ECE
COL_AI = 0x00CEE2EC
COL_BLUE = 0x00CE7E08

CFG_BASE = (20, 130, CW - 20, 166)
CFG_MODEL = (20, 220, CW - 20, 256)
CFG_KEY = (20, 310, CW - 20, 346)
CFG_SAVE = (20, 400, CW - 20, 444)


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
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [wt.HWND, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]


def _in(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


class ChatWindow:
    def __init__(self, pet):
        self.pet = pet
        self.alive = False
        self.state = "chat" if pet.chat.available() else "config"
        self.hwnd = self.edit = self.f_base = self.f_model = self.f_key = None
        self._font = self._old_proc = self._proc_ref = self._edit_ref = None
        self._build()

    def _make_edit(self, rect, secure=False):
        style = WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL
        if secure:
            style |= 0x0020
        e = user32.CreateWindowExW(
            WS_EX_CLIENTEDGE, "EDIT", "", style,
            rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1],
            self.hwnd, None, W.kernel32.GetModuleHandleW(None), None)
        user32.SendMessageW(e, WM_SETFONT, int(self._font), 1)
        return e

    def _build(self):
        hinst = W.kernel32.GetModuleHandleW(None)
        cls = "BearChatWindow"
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        self._proc_ref = W.WNDPROC(self._proc)
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.cast(32512, wt.LPCWSTR))
        wc.lpszClassName = cls
        wc.hbrBackground = gdi32.CreateSolidBrush(COL_BG)
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:
                raise ctypes.WinError(err)
        self.hwnd = user32.CreateWindowExW(
            W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW, cls, "和自嘲熊聊聊", WS_POPUP,
            0, 0, CW, CH, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._font = gdi32.CreateFontW(-15, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, FONT_NAME)
        self.edit = self._make_edit((14, INPUT_Y, CW - 28, INPUT_Y + 32))
        self.f_base = self._make_edit(CFG_BASE)
        self.f_model = self._make_edit(CFG_MODEL)
        self.f_key = self._make_edit(CFG_KEY, secure=True)

        cfg = self.pet._load_config().get("llm") or {}
        self._set_text(self.f_base, str(cfg.get("base_url") or ""))
        self._set_text(self.f_model, str(cfg.get("model") or ""))
        self._set_text(self.f_key, str(cfg.get("api_key") or ""))

        self._edit_ref = W.WNDPROC(self._edit_proc)
        self._old_proc = user32.SetWindowLongPtrW(
            self.edit, GWLP_WNDPROC, ctypes.cast(self._edit_ref, ctypes.c_void_p))
        self._apply_state()

    def _set_text(self, hwnd, value):
        buf = ctypes.create_unicode_buffer(value)
        user32.SendMessageW(hwnd, WM_SETTEXT, 0,
                            ctypes.cast(buf, ctypes.c_void_p).value)

    def _get_text(self, hwnd):
        n = int(user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0))
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.SendMessageW(hwnd, WM_GETTEXT, n + 1,
                            ctypes.cast(buf, ctypes.c_void_p).value)
        return buf.value.strip()

    def _edit_proc(self, hwnd, msg, wp, lp):
        if msg == WM_KEYDOWN:
            if wp == VK_RETURN:
                if self.state == "config":
                    self.save_config()
                else:
                    self.send()
                return 0
            if wp == VK_ESCAPE:
                self.close()
                return 0
        return user32.CallWindowProcW(self._old_proc, hwnd, msg, wp, lp)

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
                self.click(x, y)
                return 0
            if msg == W.WM_NCHITTEST:
                y = ctypes.c_short((lp >> 16) & 0xFFFF).value
                if y < 30:
                    return HTCAPTION
        except Exception:
            import traceback
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def _apply_state(self):
        config = self.state == "config"
        for h, show in ((self.edit, not config), (self.f_base, config),
                        (self.f_model, config), (self.f_key, config)):
            user32.ShowWindow(h, SW_SHOW if show else SW_HIDE)

    def click(self, x, y):
        if self.state == "config":
            if _in(CFG_SAVE, x, y):
                self.save_config()
        elif y >= INPUT_Y:
            user32.SetFocus(self.edit)

    def save_config(self):
        base = self._get_text(self.f_base)
        model = self._get_text(self.f_model)
        key = self._get_text(self.f_key)
        if not base or not model or not key:
            self.pet.brain.say("三个都填上才行哦", 3.0)
            return
        self.pet.set_llm_config({"base_url": base, "model": model, "api_key": key})
        self.state = "chat"
        self._apply_state()
        self._repaint()
        self.pet.brain.say("配置好了，聊吧", 2.5)

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            bg = gdi32.CreateSolidBrush(COL_BG)
            user32.FillRect(hdc, ctypes.byref(wt.RECT(0, 0, CW, CH)), bg)
            gdi32.DeleteObject(bg)
            gdi32.SelectObject(hdc, self._font)
            gdi32.SetBkMode(hdc, TRANSPARENT)

            def text(x, y, w, h, s, color=COL_INK, align=DT_LEFT):
                gdi32.SetTextColor(hdc, color)
                r = wt.RECT(x, y, x + w, y + h)
                user32.DrawTextW(hdc, s, len(s), ctypes.byref(r),
                                 align | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)

            if self.state == "config":
                text(20, 108, 300, 18, "接口地址 (base_url)", COL_DIM)
                text(20, 198, 300, 18, "模型名 (model)", COL_DIM)
                text(20, 288, 300, 18, "API Key", COL_DIM)
                self._round(hdc, CFG_SAVE, COL_BLUE, COL_BLUE)
                text(CFG_SAVE[0] + 12, CFG_SAVE[1] + 12, 200, 24,
                     "保存并开始聊天", 0x00FFFFFF)
                return

            text(14, 6, 200, 24, "和自嘲熊聊聊", COL_INK)
            text(CW - 150, 8, 138, 20, "Enter 发送 · Esc 关闭", COL_DIM)
            y = 36
            for m in list(self.pet.chat.memory.messages)[-12:]:
                me = m["role"] == "user"
                text(14 if me else CW - 30, y, 16, 18,
                     "我" if me else "熊", COL_DIM)
                y += 18
                lines = m["content"].split("\n")
                bh = 12 + len(lines) * 20
                self._round(hdc, (14, y, CW - 14, y + bh),
                            COL_ME if me else COL_AI, COL_ME if me else COL_AI)
                for i, line in enumerate(lines[:6]):
                    text(22, y + 6 + i * 20, CW - 44, 20, line,
                         0x00FFFFFF if me else COL_INK)
                y += bh + 12
                if y > INPUT_Y - 30:
                    break
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    def _round(self, hdc, rect, fill, outline):
        pen = gdi32.CreatePen(0, 1, outline)
        oldp = gdi32.SelectObject(hdc, pen)
        brush = gdi32.CreateSolidBrush(fill)
        oldb = gdi32.SelectObject(hdc, brush)
        gdi32.RoundRect(hdc, rect[0], rect[1], rect[2], rect[3], 8, 8)
        gdi32.SelectObject(hdc, oldp)
        gdi32.SelectObject(hdc, oldb)
        gdi32.DeleteObject(pen)
        gdi32.DeleteObject(brush)

    def _repaint(self):
        user32.InvalidateRect(self.hwnd, None, True)
        user32.UpdateWindow(self.hwnd)

    def send(self):
        text = self._get_text(self.edit)
        if not text:
            return
        self._set_text(self.edit, "")
        self.pet.brain.say(text, 2.0)
        self.pet.chat.send(text, on_done=self._on_reply, on_error=self._on_error)
        self._repaint()

    def _on_reply(self, reply):
        self._repaint()
        self.pet.brain.say(reply, 5.0)

    def _on_error(self, msg):
        self._repaint()
        self.pet.brain.say(msg, 3.0)

    def open(self, near_x: float, near_y: float):
        left, top, right, bottom = W.work_area(self.pet.win.hwnd)
        x = int(max(left + 8, min(right - CW - 8, near_x)))
        y = int(max(top + 8, min(bottom - CH - 8, near_y)))
        user32.SetWindowPos(self.hwnd, W.HWND_TOPMOST, x, y, CW, CH, 0x0040)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        user32.SetFocus(self.edit if self.state == "chat" else self.f_key)
        self.alive = True
        self._apply_state()
        self._repaint()

    def close(self):
        self.alive = False
        self.pet.chat_open = False
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def destroy(self):
        try:
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        except Exception:
            pass
