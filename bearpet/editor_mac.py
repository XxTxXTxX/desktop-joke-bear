"""添加提醒的小窗口（macOS）：NSPanel + NSTextField。

背景与按钮用 PIL 画成一张位图（和 Win32 版同一套版式/配色），真正的"打字"
交给 NSTextField，因此中文输入法、光标、选区、粘贴全部是系统原生行为。

交互：Enter = 添加，Esc = 取消，拖标题区域可移动。
"""
from __future__ import annotations

import time

from objc import super as objc_super
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBitmapImageRep,
    NSColor,
    NSDeviceRGBColorSpace,
    NSFont,
    NSFloatingWindowLevel,
    NSMakeRect,
    NSPanel,
    NSSound,
    NSTextField,
    NSView,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject
from PIL import Image, ImageChops, ImageDraw

from . import art, maclayer as W

CW, CH = 392, 300
COL_BG = (236, 242, 246)
COL_INK = (8, 12, 26)
COL_DIM = (74, 90, 106)
COL_LINE = (217, 207, 194)
COL_ON_BG = (255, 233, 201)
COL_ON_INK = (138, 90, 12)
COL_PRIMARY = (206, 126, 5)

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


def _chips(items, y, x0=16, h=26, gap=8):
    out, x = [], x0
    for label, value in items:
        wide = any(ord(c) > 127 for c in label)
        w = 22 + len(label) * 14 if wide else 18 + len(label) * 8
        out.append(((x, y, x + w, y + h), label, value))
        x += w + gap
    return out


def _to_rep(img):
    a = img.getchannel("A")
    premul = Image.merge("RGBA", (
        ImageChops.multiply(img.getchannel("R"), a),
        ImageChops.multiply(img.getchannel("G"), a),
        ImageChops.multiply(img.getchannel("B"), a),
        a,
    )).tobytes("raw", "RGBA")
    w, h = img.size
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, w, h, 8, 4, True, False, NSDeviceRGBColorSpace, w * 4, 32)
    rep.bitmapData()[:] = premul
    return rep


class _EditorPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class _FieldDelegate(NSObject):
    def initWithOwner_(self, owner):
        self = objc_super(_FieldDelegate, self).init()
        self._owner = owner
        return self

    def control_textView_doCommandBySelector_(self, control, textView, selector):
        sel = str(selector)
        if sel == "insertNewline:":
            self._owner.commit()
            return True
        if sel == "cancelOperation:":
            self._owner.close()
            return True
        return False


class _EditorView(NSView):
    def isFlipped(self):
        return True

    def initWithOwner_(self, owner):
        self = objc_super(_EditorView, self).initWithFrame_(
            NSMakeRect(0, 0, CW, CH))
        self._owner = owner
        self._drag_from = None
        return self

    def drawRect_(self, rect):
        rep = self._owner._background
        if rep is not None:
            rep.drawInRect_(self.bounds())

    def mouseDown_(self, event):
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        x, y = int(p.x), int(p.y)
        if y < 32:
            win = self._owner.hwnd
            f = win.frame()
            self._drag_from = (x, y, f.origin.x, f.origin.y)
            return
        self._owner._click(x, y)

    def mouseDragged_(self, event):
        if self._drag_from is None:
            return
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        x0, y0, wx, wy = self._drag_from
        self._owner.hwnd.setFrameOrigin_((wx + p.x - x0, wy - (p.y - y0)))

    def mouseUp_(self, event):
        self._drag_from = None


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
        self._background = None
        self._build()

    def _build(self):
        self.hwnd = _EditorPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, CW, CH), NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False)
        self.hwnd.setOpaque_(False)
        self.hwnd.setBackgroundColor_(NSColor.clearColor())
        self.hwnd.setHasShadow_(True)
        self.hwnd.setLevel_(NSFloatingWindowLevel)
        self.hwnd.setFloatingPanel_(True)
        self.hwnd.setHidesOnDeactivate_(False)
        self._view = _EditorView.alloc().initWithOwner_(self)
        self.hwnd.setContentView_(self._view)

        self._delegate = _FieldDelegate.alloc().initWithOwner_(self)
        self.edit_msg = self._make_field(*MSG_BOX)
        self.edit_time = self._make_field(*CUSTOM_EDIT)
        self._render_bg()

    def _make_field(self, x, y1, x2, y2):
        w, h = x2 - x, y2 - y1
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y1, w, h))
        f.setBezeled_(True)
        f.setDrawsBackground_(True)
        f.setEditable_(True)
        f.setSelectable_(True)
        f.setFont_(NSFont.systemFontOfSize_(14))
        f.setDelegate_(self._delegate)
        self._view.addSubview_(f)
        return f

    # ------------------------------------------------------------ 绘制
    def _render_bg(self):
        img = Image.new("RGBA", (CW, CH), COL_BG + (255,))
        d = ImageDraw.Draw(img)
        font = art._font(14)
        small = art._font(12)

        def text(x, y, w, h, s, color=COL_INK, center=True):
            box = d.textbbox((0, 0), s, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
            tx = x + (w - tw) / 2 if center else x
            ty = y + (h - th) / 2 - box[1]
            d.text((tx, ty), s, font=font, fill=color + (255,))

        d.text((16, 8), "添加提醒", font=font, fill=COL_DIM + (255,))
        d.text((200, 8), "Enter 添加 / Esc 取消", font=small, fill=(122, 138, 154, 255))

        def chips(items, sel):
            for i, (r, label, _v) in enumerate(items):
                x0, y0, x1, y1 = r
                on = (i == sel) if sel is not None else False
                d.rounded_rectangle([x0, y0, x1, y1], radius=10,
                                    fill=COL_ON_BG if on else (248, 251, 253, 255),
                                    outline=(8, 18, 51, 255) if on else COL_LINE + (255,),
                                    width=2)
                text(x0, y0, x1 - x0, y1 - y0, label,
                     COL_ON_INK if on else COL_INK)

        chips(self.quick, None)
        text(16, TIME_LABEL_Y - 2, 120, 20, "什么时候", COL_DIM, center=False)
        chips(self.times, self.sel_time)
        text(16, CUSTOM_LABEL_Y, 84, 22, "或填 HH:MM", COL_DIM, center=False)
        text(16, REP_LABEL_Y - 2, 120, 20, "重复", COL_DIM, center=False)
        chips(self.reps, self.sel_rep)

        for rect, label, primary in ((self.btn_cancel, "取消", False),
                                     (self.btn_ok, "添加", True)):
            x0, y0, x1, y1 = rect
            d.rounded_rectangle([x0, y0, x1, y1], radius=12,
                                fill=COL_PRIMARY if primary else (248, 251, 253, 255),
                                outline=(8, 18, 51, 255), width=2)
            text(x0, y0, x1 - x0, y1 - y0, label,
                 (255, 255, 255) if primary else COL_INK)

        self._background = _to_rep(img.transpose(Image.FLIP_TOP_BOTTOM))
        self._view.setNeedsDisplay_(True)

    # ------------------------------------------------------------ 交互
    def _hit(self, x, y):
        for group, kind in ((self.quick, "quick"), (self.times, "time"),
                            (self.reps, "rep")):
            for i, (r, _l, _v) in enumerate(group):
                if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                    return kind, i
        for rect, kind in ((self.btn_ok, "ok"), (self.btn_cancel, "cancel")):
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                return kind, 0
        return None

    def _click(self, x, y):
        hit = self._hit(x, y)
        if hit is None:
            return
        kind, idx = hit
        if kind == "quick":
            self.edit_msg.setStringValue_(self.quick[idx][2])
            self.hwnd.makeFirstResponder_(self.edit_msg)
        elif kind == "time":
            self.sel_time = idx
            self.edit_time.setStringValue_("")
            self._render_bg()
        elif kind == "rep":
            self.sel_rep = idx
            self._render_bg()
        elif kind == "ok":
            self.commit()
        elif kind == "cancel":
            self.close()

    def _get(self, field) -> str:
        return str(field.stringValue() or "").strip()

    def commit(self):
        text = self._get(self.edit_msg)
        if not text:
            NSSound.beep()
            self.hwnd.makeFirstResponder_(self.edit_msg)
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

    def open(self, near_x: float, near_y: float):
        left, top, right, bottom = W.work_area(self.pet.win.hwnd)
        x = int(max(left + 8, min(right - CW - 8, near_x)))
        y = int(max(top + 8, min(bottom - CH - 8, near_y)))
        self.edit_msg.setStringValue_("")
        self.edit_time.setStringValue_("")
        self.sel_time, self.sel_rep = 1, 0
        self._render_bg()
        self.hwnd.setFrameOrigin_((x, W._global_top() - y - CH))
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        self.hwnd.makeKeyAndOrderFront_(None)
        self.hwnd.makeFirstResponder_(self.edit_msg)
        self.alive = True

    def close(self):
        self.alive = False
        self.pet.editor_open = False
        self.hwnd.orderOut_(None)
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory)

    def destroy(self):
        try:
            win = self.hwnd
            if win is not None:
                win.orderOut_(None)
                win.close()
                self.hwnd = None
        except Exception:
            pass
