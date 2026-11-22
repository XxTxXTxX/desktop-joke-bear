"""macOS 窗口后端 —— AppKit 实现的逐像素透明桌宠窗口。

与 Win32 分层窗口等价的行为：
  * NSWindow(borderless) + 非不透明 + clearColor → 真正的逐像素 alpha；
  * NSView.hitTest 按 alpha 返回 None → 透明区域鼠标穿透；
  * canBecomeKeyWindow / canBecomeMain = False → 点熊不抢焦点、不进 Dock；
  * level = NSFloatingWindowLevel + orderFrontRegardless → 像 HWND_TOPMOST 一样置顶；
  * 手动 nextEventMatchingMask + sendEvent → 与 PeekMessage 同构的消息泵。

对外暴露与 winlayer_win.py 完全相同的 API。
"""
from __future__ import annotations

import sys
import time
import traceback

from objc import super as objc_super
from PIL import Image, ImageChops

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBitmapImageRep,
    NSCursor,
    NSDeviceRGBColorSpace,
    NSMenu,
    NSMenuItem,
    NSNonactivatingPanelMask,
    NSPanel,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSEvent,
    NSEventMaskLeftMouseDragged,
    NSEventMaskLeftMouseUp,
    NSEventMaskMouseMoved,
    NSEventMaskRightMouseUp,
    NSEventTypeLeftMouseDragged,
    NSEventTypeLeftMouseUp,
    NSEventTypeMouseMoved,
    NSBackingStoreBuffered,
    NSScreen,
    NSRunLoop,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseMoved,
    NSObject,
    NSTimer,
    NSRunLoopCommonModes,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSFloatingWindowLevel,
    NSColor,
    NSView,
)
from Foundation import NSMakePoint, NSMakeRect, NSPointInRect

HWND_TOPMOST = -1
NATIVE_RUN_LOOP = True
ON_EXIT = None


def set_on_exit(cb):
    global ON_EXIT
    ON_EXIT = cb

# 与 Win32 常量保持同名，调试工具/旧代码若引用也不会 AttributeError
WS_POPUP = 0x80000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

_APP = NSApplication.sharedApplication()
try:
    _APP.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
except Exception:
    pass
try:
    _APP.finishLaunching()
except Exception:
    pass

_WINDOWS = {}


def _safe(fn, *args):
    if fn is None:
        return
    try:
        fn(*args)
    except Exception:
        traceback.print_exc()


def _global_top() -> float:
    """虚拟桌面最上边的 y（macOS 原生坐标原点在左下角）。"""
    top = float("-inf")
    for s in NSScreen.screens() or []:
        f = s.frame()
        top = max(top, f.origin.y + f.size.height)
    if top == float("-inf"):
        return 0.0
    return top


def _screen_for(hwnd):
    owner = _WINDOWS.get(hwnd)
    if owner is not None:
        x = owner.x + owner.width / 2.0
        y = _global_top() - (owner.y + owner.height / 2.0)
        point = NSMakePoint(x, y)
    else:
        point = NSEvent.mouseLocation()
    screens = NSScreen.screens() or []
    if not screens:
        return NSScreen.mainScreen()
    for s in screens:
        if NSPointInRect(point, s.frame()):
            return s
    best, best_d = screens[0], float("inf")
    for s in screens:
        f = s.frame()
        cx, cy = f.origin.x + f.size.width / 2.0, f.origin.y + f.size.height / 2.0
        d = (point.x - cx) ** 2 + (point.y - cy) ** 2
        if d < best_d:
            best, best_d = s, d
    return best


def cursor_pos() -> tuple[int, int]:
    p = NSEvent.mouseLocation()
    return int(round(p.x)), int(round(_global_top() - p.y))


def left_button_down() -> bool:
    return bool(NSEvent.pressedMouseButtons() & 1)


def work_area(hwnd) -> tuple[int, int, int, int]:
    """返回窗口所在显示器可用区，坐标换算成虚拟桌面左上角原点。"""
    screen = _screen_for(hwnd)
    if screen is None:
        return 0, 0, 1920, 1040
    f = screen.visibleFrame()
    top = _global_top()
    return (int(round(f.origin.x)),
            int(round(top - (f.origin.y + f.size.height))),
            int(round(f.origin.x + f.size.width)),
            int(round(top - f.origin.y)))


def _monitor_mask():
    return (NSEventMaskLeftMouseUp | NSEventMaskLeftMouseDragged |
            NSEventMaskMouseMoved | NSEventMaskRightMouseUp)


class _BearView(NSView):
    def initWithOwner_(self, owner):
        self = objc_super(_BearView, self).initWithFrame_(
            NSMakeRect(0, 0, owner.width, owner.height))
        if self is None:
            return None
        self._owner = owner
        self.setWantsLayer_(True)
        try:
            opts = NSTrackingMouseMoved | NSTrackingActiveAlways | NSTrackingInVisibleRect
            area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                NSMakeRect(0, 0, owner.width, owner.height), opts, self, None)
            self.addTrackingArea_(area)
        except Exception:
            pass
        return self

    def isFlipped(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def acceptsFirstResponder(self):
        return True

    def resetCursorRects(self):
        self.addCursorRect_cursor_(self.bounds(), NSCursor.pointingHandCursor())

    def drawRect_(self, rect):
        rep = self._owner._rep
        if rep is not None:
            rep.drawInRect_(self.bounds())

    def hitTest_(self, point):
        owner = self._owner
        if owner is None:
            return None
        if owner._capturing:
            return self
        local = self.convertPoint_fromView_(point, None)
        x = int(local.x)
        y = int(local.y)
        if owner._hit_opaque(x, y):
            return self
        return None

    def mouseDown_(self, event):
        owner = self._owner
        owner._capturing = True
        owner._install_monitor()
        sx, sy = cursor_pos()
        _safe(owner.on_left_down, sx, sy)
        if event.clickCount() >= 2:
            _safe(owner.on_double_click, sx, sy)

    def mouseUp_(self, event):
        owner = self._owner
        if not owner._capturing:
            return
        owner._capturing = False
        owner._remove_monitor()
        _safe(owner.on_left_up, *cursor_pos())

    def mouseDragged_(self, event):
        _safe(self._owner.on_move, *cursor_pos())

    def mouseMoved_(self, event):
        _safe(self._owner.on_move, *cursor_pos())

    def rightMouseDown_(self, event):
        owner = self._owner
        owner._right_pressed = True
        _safe(owner.on_right_up, *cursor_pos())

    def rightMouseUp_(self, event):
        self._owner._right_pressed = False


class _BearWindow(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False


class LayeredWindow:
    """一块逐像素透明的独立窗口，内容由 PIL 图像逐帧推送。"""

    def __init__(self, width: int, height: int, title: str = "bearpet",
                 click_handlers: bool = True, auto_show: bool = True):
        self.width = int(width)
        self.height = int(height)
        self.x = -10000
        self.y = -10000
        self.alive = True
        self._shown = False
        self._want_visible = bool(auto_show)
        self._alpha = bytes(self.width * self.height)
        self._rep = None
        self._pixel_size = None
        self._capturing = False
        self._right_pressed = False
        self._last_pos = None
        self._monitor = None
        self._scale = 1.0
        try:
            self._scale = float(NSScreen.mainScreen().backingScaleFactor() or 1.0)
        except Exception:
            pass

        self.on_left_down = None
        self.on_left_up = None
        self.on_move = None
        self.on_right_up = None
        self.on_double_click = None

        rect = NSMakeRect(0, 0, self.width, self.height)
        self.hwnd = _BearWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless | NSNonactivatingPanelMask,
            NSBackingStoreBuffered, False)
        self.hwnd.setBecomesKeyOnlyIfNeeded_(True)
        win = self.hwnd
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setHasShadow_(False)
        win.setLevel_(NSFloatingWindowLevel)
        win.setIgnoresMouseEvents_(False)
        win.setAcceptsMouseMovedEvents_(True)
        win.setAlphaValue_(1.0)
        try:
            win.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorStationary |
                NSWindowCollectionBehaviorIgnoresCycle)
        except Exception:
            pass
        self._view = _BearView.alloc().initWithOwner_(self)
        win.setContentView_(self._view)
        win.setFrameOrigin_(NSMakePoint(self.x, _global_top() - self.y - self.height))
        _WINDOWS[win] = self

    # ---- 鼠标穿透 / 捕获 --------------------------------------------
    def _alpha_at(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._alpha[y * self.width + x]
        return 0

    def _hit_opaque(self, x: int, y: int) -> bool:
        if self._alpha_at(x, y) > 1:
            return True
        for dx, dy in ((4, 0), (-4, 0), (0, 4), (0, -4),
                       (4, 4), (-4, -4), (4, -4), (-4, 4)):
            if self._alpha_at(x + dx, y + dy) > 1:
                return True
        return False

    def _install_monitor(self):
        if self._monitor is not None:
            return
        owner = self

        def handler(event):
            try:
                t = event.type()
                if t == NSEventTypeLeftMouseDragged:
                    owner.mouse_dragged_external()
                elif t == NSEventTypeLeftMouseUp:
                    owner.mouse_up_external()
                elif t == NSEventTypeMouseMoved:
                    _safe(owner.on_move, *cursor_pos())
            except Exception:
                traceback.print_exc()
            return event

        try:
            self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                _monitor_mask(), handler)
        except Exception:
            self._monitor = None

    def _remove_monitor(self):
        if self._monitor is not None:
            try:
                NSEvent.removeMonitor_(self._monitor)
            except Exception:
                pass
            self._monitor = None

    def mouse_dragged_external(self):
        if self._capturing:
            _safe(self.on_move, *cursor_pos())

    def mouse_up_external(self):
        if self._capturing:
            self._capturing = False
            self._remove_monitor()
            _safe(self.on_left_up, *cursor_pos())

    # ---- 消息泵 -----------------------------------------------------
    def pump(self) -> bool:
        return self.alive

    # ---- 绘制 -------------------------------------------------------
    def blit(self, img, x: int | None = None, y: int | None = None):
        w, h = img.size
        if x is not None:
            self.x = int(x)
        if y is not None:
            self.y = int(y)
        if w != self.width or h != self.height:
            self.width, self.height = w, h
            self._view.setFrame_(NSMakeRect(0, 0, w, h))

        self._alpha = img.getchannel("A").tobytes()
        scale = self._scale
        disp = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS) if scale != 1.0 else img
        disp = disp.transpose(Image.FLIP_TOP_BOTTOM)
        dw, dh = disp.size
        a = disp.getchannel("A")
        premul = Image.merge("RGBA", (
            ImageChops.multiply(disp.getchannel("R"), a),
            ImageChops.multiply(disp.getchannel("G"), a),
            ImageChops.multiply(disp.getchannel("B"), a),
            a,
        )).tobytes("raw", "RGBA")

        if self._rep is None or self._pixel_size != (dw, dh):
            self._rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                None, dw, dh, 8, 4, True, False, NSDeviceRGBColorSpace, dw * 4, 32)
            self._view.layer().setContentsScale_(scale)
            self._pixel_size = (dw, dh)
        self._rep.bitmapData()[:] = premul
        self._view.setNeedsDisplay_(True)

        px, py = self.x, _global_top() - self.y - h
        target = (px, py)
        if self._last_pos != target:
            if self._shown:
                self.hwnd.setFrameOrigin_(NSMakePoint(px, py))
            else:
                self.hwnd.setFrame_display_(NSMakeRect(px, py, w, h), False)
            self._last_pos = target
        if self._want_visible and not self._shown:
            self.show()

    def move(self, x: int, y: int):
        self.x, self.y = int(x), int(y)
        self.hwnd.setFrameOrigin_(NSMakePoint(self.x, _global_top() - self.y - self.height))

    def raise_topmost(self):
        self.hwnd.setLevel_(NSFloatingWindowLevel)
        self.hwnd.orderFrontRegardless()

    def show(self):
        self.hwnd.orderFrontRegardless()
        self._shown = True
        self._want_visible = True

    def hide(self):
        self.hwnd.orderOut_(None)
        self._shown = False
        self._want_visible = False

    @property
    def visible(self) -> bool:
        return self._shown and self._want_visible

    def work_area(self):
        return work_area(self.hwnd)

    def destroy(self):
        self._remove_monitor()
        self._capturing = False
        win = self.hwnd
        if win is not None:
            _WINDOWS.pop(win, None)
            win.orderOut_(None)
            win.close()
            self.hwnd = None
        self.alive = False


class _TickTarget(NSObject):
    def initWithCallback_(self, cb):
        self = objc_super(_TickTarget, self).init()
        self._callback = cb
        return self

    def tick_(self, timer):
        self._callback()


_RUN_REF = {}


class _StatusTarget(NSObject):
    def initWithPet_(self, pet):
        self = objc_super(_StatusTarget, self).init()
        self._pet = pet
        return self

    def quitBear_(self, sender):
        self._pet.running = False


def _install_status_item(pet):
    if "status" in _RUN_REF:
        return
    target = _StatusTarget.alloc().initWithPet_(pet)
    status = NSStatusBar.systemStatusBar().statusItemWithLength_(
        NSVariableStatusItemLength)
    status.button().setTitle_("熊")
    menu = NSMenu.alloc().init()
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "退出自嘲熊", "quitBear:", "")
    item.setTarget_(target)
    menu.addItem_(item)
    status.setMenu_(menu)
    _RUN_REF["status"] = status
    _RUN_REF["status_target"] = target


def run_forever(pet):
    """用 NSApplication 真正的事件循环驱动主程序，保证窗口激活与 IME 可用。"""
    state = {"last": time.perf_counter(), "fps": 45}

    def frame():
        now = time.perf_counter()
        dt = min(0.05, now - state["last"])
        state["last"] = now
        if not pet.running:
            try:
                pet.shutdown()
            except Exception:
                traceback.print_exc()
            try:
                if callable(ON_EXIT):
                    ON_EXIT()
            except Exception:
                traceback.print_exc()
            _APP.terminate_(None)
            return
        try:
            pet.update(dt)
            pet.draw()
        except Exception:
            traceback.print_exc()
            pet.running = False

    target = _TickTarget.alloc().initWithCallback_(frame)
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1.0 / state["fps"], target, "tick:", None, True)
    NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
    _RUN_REF["target"] = target
    _RUN_REF["timer"] = timer
    try:
        _install_status_item(pet)
    except Exception:
        traceback.print_exc()
    _APP.run()
