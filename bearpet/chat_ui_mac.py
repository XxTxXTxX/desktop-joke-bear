"""聊天窗口（macOS）：NSPanel + NSTextField，对话记录用 PIL 绘制。"""
from __future__ import annotations

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
    NSSecureTextField,
    NSTextField,
    NSView,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import art, chat as chatmod, maclayer as W

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
GREEN = (60, 175, 120)

CFG_BASE = (20, 130, CW - 20, 166)
CFG_MODEL = (20, 220, CW - 20, 256)
CFG_KEY = (20, 310, CW - 20, 346)
CFG_SAVE = (20, 400, CW - 20, 444)


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


def _rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                                           radius=radius, fill=255)
    img.putalpha(mask)
    return img


class _ChatFieldDelegate(NSObject):
    def initWithOwner_(self, owner):
        self = objc_super(_ChatFieldDelegate, self).init()
        self._owner = owner
        return self

    def control_textView_doCommandBySelector_(self, control, textView, selector):
        sel = str(selector)
        if sel == "insertNewline:":
            if self._owner.state == "config":
                self._owner.save_config()
            else:
                self._owner.send()
            return True
        if sel == "cancelOperation:":
            self._owner.close()
            return True
        return False


class _ChatView(NSView):
    def isFlipped(self):
        return True

    def initWithOwner_(self, owner):
        self = objc_super(_ChatView, self).initWithFrame_(NSMakeRect(0, 0, CW, CH))
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
        if y < HEADER_H:
            f = self._owner.hwnd.frame()
            self._drag_from = (x, y, f.origin.x, f.origin.y)
            return
        self._owner.click(x, y)

    def mouseDragged_(self, event):
        if self._drag_from is None:
            return
        p = self.convertPoint_fromView_(event.locationInWindow(), None)
        x0, y0, wx, wy = self._drag_from
        self._owner.hwnd.setFrameOrigin_((wx + p.x - x0, wy - (p.y - y0)))

    def mouseUp_(self, event):
        self._drag_from = None


class _ChatPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


def _in(rect, x, y):
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


class ChatWindow:
    def __init__(self, pet):
        self.pet = pet
        self.alive = False
        self._background = None
        self.state = "chat" if pet.chat.available() else "config"
        self._build()

    def _make_field(self, rect, font_size=14, secure=False):
        cls = NSSecureTextField if secure else NSTextField
        f = cls.alloc().initWithFrame_(
            NSMakeRect(rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]))
        f.setBezeled_(False)
        f.setDrawsBackground_(True)
        f.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.96, 1.0))
        f.setFont_(NSFont.systemFontOfSize_(font_size))
        f.setDelegate_(self._delegate)
        f.setFocusRingType_(1)
        self._view.addSubview_(f)
        return f

    def _build(self):
        self.hwnd = _ChatPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, CW, CH), NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False)
        self.hwnd.setOpaque_(False)
        self.hwnd.setBackgroundColor_(NSColor.clearColor())
        self.hwnd.setHasShadow_(True)
        self.hwnd.setLevel_(NSFloatingWindowLevel)
        self.hwnd.setFloatingPanel_(True)
        self._view = _ChatView.alloc().initWithOwner_(self)
        self.hwnd.setContentView_(self._view)
        self._delegate = _ChatFieldDelegate.alloc().initWithOwner_(self)

        self.input = self._make_field((20, INPUT_Y + 8, CW - 96, INPUT_Y + 44))
        self.f_base = self._make_field(CFG_BASE, 12)
        self.f_model = self._make_field(CFG_MODEL, 12)
        self.f_key = self._make_field(CFG_KEY, 12, secure=True)
        cfg = self.pet._load_config().get("llm") or {}
        self.f_base.setStringValue_(str(cfg.get("base_url") or ""))
        self.f_model.setStringValue_(str(cfg.get("model") or ""))
        self.f_key.setStringValue_(str(cfg.get("api_key") or ""))

        self._apply_state()
        self._render()

    def _apply_state(self):
        config = self.state == "config"
        self.input.setHidden_(config)
        self.f_base.setHidden_(not config)
        self.f_model.setHidden_(not config)
        self.f_key.setHidden_(not config)
        if config:
            self.hwnd.makeFirstResponder_(self.f_key)

    def click(self, x, y):
        if self.state == "config":
            if _in(CFG_SAVE, x, y):
                self.save_config()
            elif _in(CFG_BASE, x, y):
                self.hwnd.makeFirstResponder_(self.f_base)
            elif _in(CFG_MODEL, x, y):
                self.hwnd.makeFirstResponder_(self.f_model)
            elif _in(CFG_KEY, x, y):
                self.hwnd.makeFirstResponder_(self.f_key)
        else:
            if _in((CW - 88, INPUT_Y + 6, CW - 18, INPUT_Y + 46), x, y):
                self.send()
            elif _in((20, INPUT_Y + 8, CW - 96, INPUT_Y + 44), x, y):
                self.hwnd.makeFirstResponder_(self.input)

    def save_config(self):
        base = str(self.f_base.stringValue() or "").strip()
        model = str(self.f_model.stringValue() or "").strip()
        key = str(self.f_key.stringValue() or "").strip()
        if not base or not model or not key:
            self.pet.brain.say("三个都填上才行哦", 3.0)
            return
        self.pet.set_llm_config({"base_url": base, "model": model, "api_key": key})
        self.state = "chat"
        self._apply_state()
        self._render()
        self.pet.brain.say("配置好了，聊吧", 2.5)

    def _header(self, d, title, subtitle):
        d.rounded_rectangle([0, 0, CW - 1, HEADER_H], radius=RADIUS,
                            fill=HEADER + (255,))
        d.rectangle([0, HEADER_H - RADIUS, CW - 1, HEADER_H], fill=HEADER + (255,))
        d.ellipse([18, 18, 40, 40], fill=(225, 130, 55, 255))
        d.ellipse([24, 24, 34, 34], fill=(255, 235, 180, 255))
        d.text((50, 13), title, font=art._font(17), fill=HEADER_TEXT + (255,))
        d.text((50, 35), subtitle, font=art._font(11),
               fill=(180, 165, 148, 255))

    def _render(self):
        img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        font = art._font(14)
        small = art._font(11)

        d.rounded_rectangle([0, 0, CW - 1, CH - 1], radius=RADIUS,
                            fill=BG + (255,))
        d.rounded_rectangle([8, HEADER_H + 4, CW - 8, INPUT_Y - 8], radius=12,
                            fill=CHAT_BG + (255,))

        if self.state == "config":
            self._header(d, "初次见面", "填好接口信息，就能和熊聊天了")
            d.text((20, 106), "接口地址 (base_url)", font=small, fill=DIM + (255,))
            d.text((20, 196), "模型名 (model)", font=small, fill=DIM + (255,))
            d.text((20, 286), "API Key", font=small, fill=DIM + (255,))
            d.rounded_rectangle(list(CFG_SAVE), radius=12, fill=BLUE + (255,))
            d.text((CFG_SAVE[0] + 16, CFG_SAVE[1] + 17), "保存并开始聊天",
                   font=art._font(15), fill=(255, 255, 255, 255))
        else:
            self._header(d, "和自嘲熊聊聊", "它记得你说过的每一句话")
            history = list(self.pet.chat.memory.messages)[-12:]
            y = HEADER_H + 18
            for m in history:
                me = m["role"] == "user"
                lines = art._wrap(m["content"], font, CW - 110)
                bw = min(CW - 96, max(70, int(max(font.getlength(l) for l in lines)) + 28))
                bh = 14 + len(lines) * 20
                bx = CW - 24 - bw if me else 24
                color = ME_BUBBLE if me else AI_BUBBLE
                d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=12,
                                    fill=color + (255,))
                d.polygon([(bx + bw - 12, y + bh - 1), (bx + bw - 2, y + bh + 8),
                           (bx + bw - 2, y + bh - 1)], fill=color + (255,)) if me else None
                for i, line in enumerate(lines):
                    d.text((bx + 14, y + 7 + i * 20), line, font=font,
                           fill=(255, 255, 255) if me else INK)
                y += bh + 12
                if y > INPUT_Y - 40:
                    break

            d.rounded_rectangle([20, INPUT_Y + 6, CW - 18, INPUT_Y + 46],
                                radius=12, fill=(255, 255, 255, 255),
                                outline=SUBTLE + (255,), width=1)
            d.rounded_rectangle([CW - 88, INPUT_Y + 6, CW - 18, INPUT_Y + 46],
                                radius=12, fill=BLUE + (255,))
            d.text((CW - 72, INPUT_Y + 16), "发送", font=art._font(14),
                   fill=(255, 255, 255, 255))

        img = _rounded(img, RADIUS)
        self._background = _to_rep(img.transpose(Image.FLIP_TOP_BOTTOM))
        self._view.setNeedsDisplay_(True)

    def send(self):
        text = str(self.input.stringValue() or "").strip()
        if not text:
            return
        self.input.setStringValue_("")
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
        self.hwnd.setFrameOrigin_((x, W._global_top() - y - CH))
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        self.hwnd.makeKeyAndOrderFront_(None)
        self._apply_state()
        self.alive = True
        self._render()

    def close(self):
        self.alive = False
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
