"""聊天窗口（Windows）：原生 EDIT 负责输入，PIL 负责绘制。

绘制部分和 macOS 版（chat_ui_mac.py）共用同一套配色、圆角、字号和排版，
避免两个平台各画一套导致"Mac 上好看，Windows 上错位"。
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes as wt

from PIL import Image, ImageDraw, ImageFont

from . import art, winlayer as W

user32 = W.user32
gdi32 = W.gdi32

WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
ES_AUTOHSCROLL = 0x0080
ES_PASSWORD = 0x0020
WM_SETFONT = 0x0030
WM_KEYDOWN = 0x0100
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_SETMARGINS = 0x00D3
EC_LEFTMARGIN = 0x0001
EC_RIGHTMARGIN = 0x0002
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
GWLP_WNDPROC = -4
HTCAPTION = 2
SW_SHOW = 5
SW_HIDE = 0
SRCCOPY = 0x00CC0020
CS_DROPSHADOW = 0x00020000

CW, CH = 420, 500
HEADER_H = 56
INPUT_Y = CH - 64
RADIUS = 16

BG = (250, 248, 245)
HEADER = (44, 36, 28)
HEADER_TEXT = (255, 250, 242)
CHAT_BG = (245, 241, 235)
ME_BUBBLE = (225, 130, 55)
AI_BUBBLE = (255, 255, 255)
INK = (48, 40, 32)
DIM = (140, 128, 114)
SUBTLE = (225, 218, 208)
BLUE = (45, 135, 210)

CFG_BASE = (20, 130, CW - 20, 166)
CFG_MODEL = (20, 220, CW - 20, 256)
CFG_KEY = (20, 310, CW - 20, 346)
CFG_SAVE = (20, 400, CW - 20, 444)

INPUT_BOX = (20, INPUT_Y + 6, CW - 18, INPUT_Y + 46)
INPUT_EDIT = (30, INPUT_Y + 12, CW - 98, INPUT_Y + 40)
SEND_BOX = (CW - 88, INPUT_Y + 6, CW - 18, INPUT_Y + 46)


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT),
                ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
                ("rgbReserved", wt.BYTE * 32)]


gdi32.CreateFontW.restype = wt.HFONT
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.BitBlt.restype = wt.BOOL
gdi32.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.CreateRoundRectRgn.restype = wt.HANDLE
gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 4 + [ctypes.c_int] * 2
user32.BeginPaint.restype = wt.HDC
# 用 c_void_p 而不是 POINTER(PAINTSTRUCT)：editor_win.py 也设置同一组
# user32 函数的 argtypes，谁后 import 谁生效，用具体结构体会互相打架。
user32.BeginPaint.argtypes = [wt.HWND, ctypes.c_void_p]
user32.EndPaint.argtypes = [wt.HWND, ctypes.c_void_p]
user32.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
user32.UpdateWindow.argtypes = [wt.HWND]
user32.SetFocus.argtypes = [wt.HWND]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [wt.HWND, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.UnregisterClassW.argtypes = [wt.LPCWSTR, wt.HINSTANCE]


NO_LINE_START = "，。、！？；：,.!?;:)]}」』）】…—"

_EMOJI_FONTS: dict[int, object] = {}


def _emoji_font(size):
    """PIL 不会自动做字体回退，emoji 在微软雅黑里是豆腐块，单独补一个。"""
    if size not in _EMOJI_FONTS:
        f = None
        for path in (r"C:\Windows\Fonts\seguiemj.ttf",
                     r"C:\Windows\Fonts\seguisym.ttf"):
            try:
                f = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
        _EMOJI_FONTS[size] = f
    return _EMOJI_FONTS[size]


def _is_emoji(ch):
    o = ord(ch)
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
            or 0x2B00 <= o <= 0x2BFF or o in (0x200D, 0x20E3, 0xFE0F))


def _wrap_line(text, font, efont, max_w):
    """按像素宽度折行，并避免行首出现句号/逗号这类标点。"""
    lines, cur, width = [], [], 0.0
    for ch in text:
        f = efont if (efont is not None and _is_emoji(ch)) else font
        w = f.getlength(ch)
        if cur and width + w > max_w and ch not in NO_LINE_START:
            lines.append(cur)
            cur, width = [], 0.0
        cur.append((ch, f))
        width += w
    lines.append(cur)
    return lines


def _line_width(line):
    return sum(f.getlength(ch) for ch, f in line)


def _in(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


class ChatWindow:
    def __init__(self, pet):
        self.pet = pet
        self.alive = False
        self.state = "chat" if pet.chat.available() else "config"
        self.hwnd = self.edit = self.f_base = self.f_model = self.f_key = None
        self._font = None
        self._hinst = None
        self._old_procs: dict[int, int] = {}
        self._lock = threading.Lock()
        self._memdc = self._screen_dc = self._hdib = self._old_bmp = None
        self._bits = ctypes.c_void_p()
        self._build()

    # ---------------------------------------------------------------- 窗口
    def _make_edit(self, rect, secure=False):
        style = WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL
        if secure:
            style |= ES_PASSWORD
        e = user32.CreateWindowExW(
            0, "EDIT", "", style,
            rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1],
            self.hwnd, None, self._hinst, None)
        if not e:
            raise ctypes.WinError(ctypes.get_last_error())
        user32.SendMessageW(e, WM_SETFONT, int(self._font), 1)
        user32.SendMessageW(e, EM_SETMARGINS, EC_LEFTMARGIN | EC_RIGHTMARGIN,
                            (8 << 16) | 8)
        return e

    def _build(self):
        hinst = W.kernel32.GetModuleHandleW(None)
        self._hinst = hinst
        cls = "BearChatWindow"
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        wc.style = CS_DROPSHADOW
        self._proc_ref = W.WNDPROC(self._proc)
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, ctypes.cast(32512, wt.LPCWSTR))
        wc.lpszClassName = cls
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(err)
        self.hwnd = user32.CreateWindowExW(
            W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW, cls, "和自嘲熊聊聊", WS_POPUP,
            0, 0, CW, CH, None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        rgn = gdi32.CreateRoundRectRgn(0, 0, CW + 1, CH + 1, RADIUS * 2, RADIUS * 2)
        if rgn:
            user32.SetWindowRgn(self.hwnd, rgn, True)

        self._font = gdi32.CreateFontW(
            -16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Microsoft YaHei")
        self.edit = self._make_edit(INPUT_EDIT)
        self.f_base = self._make_edit(CFG_BASE)
        self.f_model = self._make_edit(CFG_MODEL)
        self.f_key = self._make_edit(CFG_KEY, secure=True)

        cfg = self.pet._load_config().get("llm") or {}
        self._set_text(self.f_base, str(cfg.get("base_url") or ""))
        self._set_text(self.f_model, str(cfg.get("model") or ""))
        self._set_text(self.f_key, str(cfg.get("api_key") or ""))

        self._edit_ref = W.WNDPROC(self._edit_proc)
        for e in (self.edit, self.f_base, self.f_model, self.f_key):
            old = user32.SetWindowLongPtrW(
                e, GWLP_WNDPROC, ctypes.cast(self._edit_ref, ctypes.c_void_p))
            self._old_procs[e] = old
        self._apply_state()
        self._render()

    # ---------------------------------------------------------------- 文本
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
        old = self._old_procs.get(hwnd)
        return user32.CallWindowProcW(old, hwnd, msg, wp, lp)

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
                pt = wt.POINT(ctypes.c_short(lp & 0xFFFF).value,
                              ctypes.c_short((lp >> 16) & 0xFFFF).value)
                user32.ScreenToClient(hwnd, ctypes.byref(pt))
                if pt.y < HEADER_H:
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
        elif _in(SEND_BOX, x, y):
            self.send()
        elif y >= INPUT_Y:
            user32.SetFocus(self.edit)

    # ---------------------------------------------------------------- 绘制
    def _compose(self):
        img = Image.new("RGBA", (CW, CH), BG + (255,))
        d = ImageDraw.Draw(img)
        font = art._font(14)
        small = art._font(11)
        efont = _emoji_font(14)

        d.rounded_rectangle([0, 0, CW - 1, CH - 1], radius=RADIUS, fill=BG + (255,))
        d.rounded_rectangle([8, HEADER_H + 4, CW - 8, INPUT_Y - 8], radius=12,
                            fill=CHAT_BG + (255,))

        if self.state == "config":
            self._header(d, "初次见面", "填好接口信息，就能和熊聊天了")
            d.text((20, 106), "接口地址 (base_url)", font=small, fill=DIM)
            d.text((20, 196), "模型名 (model)", font=small, fill=DIM)
            d.text((20, 286), "API Key", font=small, fill=DIM)
            d.rounded_rectangle(list(CFG_SAVE), radius=12, fill=BLUE)
            d.text((CFG_SAVE[0] + 16, CFG_SAVE[1] + 17), "保存并开始聊天",
                   font=art._font(15), fill=(255, 255, 255))
            return img

        self._header(d, "和自嘲熊聊聊", "它记得你说过的每一句话")
        history = list(self.pet.chat.memory.messages)[-12:]
        y = HEADER_H + 18
        for m in history:
            me = m["role"] == "user"
            lines = []
            for para in str(m["content"]).split("\n"):
                lines.extend(_wrap_line(para, font, efont, CW - 110))
            widths = [_line_width(line) for line in lines]
            bw = min(CW - 96, max(70, int(max(widths)) + 28))
            bh = 14 + len(lines) * 20
            bx = CW - 24 - bw if me else 24
            color = ME_BUBBLE if me else AI_BUBBLE
            d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=12, fill=color)
            if me:
                d.polygon([(bx + bw - 12, y + bh - 1), (bx + bw - 2, y + bh + 8),
                           (bx + bw - 2, y + bh - 1)], fill=color)
            for i, line in enumerate(lines):
                x = bx + 14
                for ch, f in line:
                    d.text((x, y + 7 + i * 20), ch, font=f,
                           fill=(255, 255, 255) if me else INK)
                    x += f.getlength(ch)
            y += bh + 12
            if y > INPUT_Y - 40:
                break

        d.rounded_rectangle(list(INPUT_BOX), radius=12, fill=(255, 255, 255),
                            outline=SUBTLE, width=1)
        d.rounded_rectangle(list(SEND_BOX), radius=12, fill=BLUE)
        d.text((CW - 72, INPUT_Y + 16), "发送", font=art._font(14),
               fill=(255, 255, 255))
        return img

    def _header(self, d, title, subtitle):
        d.rounded_rectangle([0, 0, CW - 1, HEADER_H], radius=RADIUS,
                            fill=HEADER)
        d.rectangle([0, HEADER_H - RADIUS, CW - 1, HEADER_H], fill=HEADER)
        d.ellipse([18, 18, 40, 40], fill=(225, 130, 55))
        d.ellipse([24, 24, 34, 34], fill=(255, 235, 180))
        d.text((50, 13), title, font=art._font(17), fill=HEADER_TEXT)
        d.text((50, 35), subtitle, font=art._font(11), fill=(180, 165, 148))

    def _ensure_dib(self):
        if self._memdc is not None:
            return
        self._screen_dc = user32.GetDC(None)
        self._memdc = gdi32.CreateCompatibleDC(self._screen_dc)
        bmi = W.BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(W.BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = CW
        bmi.bmiHeader.biHeight = -CH
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = W.BI_RGB
        bits = ctypes.c_void_p()
        self._hdib = gdi32.CreateDIBSection(
            self._memdc, ctypes.byref(bmi), W.DIB_RGB_COLORS,
            ctypes.byref(bits), None, 0)
        if not self._hdib:
            raise ctypes.WinError(ctypes.get_last_error())
        self._bits = bits
        self._old_bmp = gdi32.SelectObject(self._memdc, self._hdib)

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

    def _render(self):
        with self._lock:
            if not self.hwnd:
                return
            img = self._compose()
            self._ensure_dib()
            data = img.tobytes("raw", "BGRA")
            ctypes.memmove(self._bits, data, len(data))
        self._repaint()

    def _paint(self, hwnd):
        ps = PAINTSTRUCT()
        hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
        try:
            if self._memdc:
                gdi32.BitBlt(hdc, 0, 0, CW, CH, self._memdc, 0, 0, SRCCOPY)
        finally:
            user32.EndPaint(hwnd, ctypes.byref(ps))

    def _repaint(self):
        if self.hwnd:
            user32.InvalidateRect(self.hwnd, None, False)
            user32.UpdateWindow(self.hwnd)

    # ---------------------------------------------------------------- 行为
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
        self._render()
        user32.SetFocus(self.edit)
        self.pet.brain.say("配置好了，聊吧", 2.5)

    def send(self):
        text = self._get_text(self.edit)
        if not text:
            return
        self._set_text(self.edit, "")
        self.pet.brain.say(text, 2.0)
        self.pet.chat.send(text, on_done=self._on_reply, on_error=self._on_error)
        self._render()

    def _on_reply(self, reply):
        self._render()
        self.pet.brain.say(reply, 5.0)

    def _on_error(self, msg):
        self._render()
        self.pet.brain.say(msg, 3.0)

    def open(self, near_x: float, near_y: float):
        left, top, right, bottom = W.work_area(self.pet.win.hwnd)
        x = int(max(left + 8, min(right - CW - 8, near_x)))
        y = int(max(top + 8, min(bottom - CH - 8, near_y)))
        user32.SetWindowPos(self.hwnd, W.HWND_TOPMOST, x, y, CW, CH, 0x0040)
        user32.ShowWindow(self.hwnd, SW_SHOW)
        user32.SetForegroundWindow(self.hwnd)
        self.alive = True
        self._apply_state()
        self._render()
        user32.SetFocus(self.edit if self.state == "chat" else self.f_key)

    def close(self):
        self.alive = False
        self.pet.chat_open = False
        if self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)

    def destroy(self):
        with self._lock:
            hwnd, self.hwnd = self.hwnd, None
        if hwnd:
            user32.DestroyWindow(hwnd)
        self._free_dib()
        if self._font:
            gdi32.DeleteObject(self._font)
            self._font = None
        if self._hinst:
            user32.UnregisterClassW("BearChatWindow", self._hinst)
            self._hinst = None
