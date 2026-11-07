#!/usr/bin/env python3
"""大肥鱼 · mac 挂件（P1）

桌面上的一只鲸鱼：
  · 按住说话 → 本地语音识别 → 送进 DSH 那间绑定的会话
  · 她的回话经本机 8778 口递回来 → 气泡显示
  · 拖着能走位；右键菜单；⌘Q 退出

协议照 DSH 插件那半边（127.0.0.1:8777）：
  POST /hands/say  {"text": "…"}
  POST 本机 8778/hands/reply  {"text": "…"}   ← 插件推过来
"""

import base64
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSMakeSize,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSPanel,
    NSStatusBar,
    NSTextField,
    NSVariableStatusItemLength,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSURL, NSLocale, NSTimer

SEND_URL = "http://127.0.0.1:8777/hands/say"
REPLY_PORT = 8778
DSH_HOME = os.environ.get("DSH_HOME") or os.path.expanduser("~/.dsh")
CONFIG_PATH = os.path.join(DSH_HOME, "fish-buddy-config.json")
SETTINGS_PATH = os.path.join(DSH_HOME, "fishbuddy-mac.json")
DEFAULT_SETTINGS = {"朗读": True, "热键": True, "陪看间隔": 20}
HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_CANDIDATES = [
    os.path.join(HERE, "assets", "whale.png"),
    os.path.join(HERE, "assets", "鱼搭子.png"),  # 本地自用
]

VERSION = "0.3.0"
BALL = 132          # 鲸鱼直径
SAMPLE_RATE = 16000
MAX_RECORD = 30.0


def log(*a):
    print("[fish]", *a, flush=True)


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        out = dict(DEFAULT_SETTINGS)
        out.update({k: v for k, v in d.items() if k in DEFAULT_SETTINGS})
        return out
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(d):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log("存设置失败", e)


def read_binding():
    """插件那半边绑了哪间会话（只读，用来告诉你没绑）"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def capture_screen(max_w=1280, quality=72):
    """截一张全屏 → base64 jpeg。mac 上要「屏幕录制」权限。"""
    fd, path = tempfile.mkstemp(suffix=".png", prefix="fishshot-")
    os.close(fd)
    try:
        r = subprocess.run(["screencapture", "-x", path], capture_output=True, timeout=15)
        if r.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 1000:
            err = (r.stderr or b"").decode("utf-8", "replace").strip()
            return None, err or "截不到屏（多半是没给「屏幕录制」权限）"
        from PIL import Image
        im = Image.open(path).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii"), None
    except Exception as e:
        return None, str(e)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


# ---------------------------------------------------------------- 录音
class Recorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.started = 0.0
        self.lock = threading.Lock()

    def start(self):
        import sounddevice as sd
        with self.lock:
            self.frames = []
            self.started = time.time()

        def cb(indata, frames, t, status):
            with self.lock:
                if self.stream is not None:
                    self.frames.append(bytes(indata))

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024, callback=cb
        )
        self.stream.start()

    def stop(self):
        """返回 wav 路径；没录到东西返回 None"""
        with self.lock:
            st, self.stream = self.stream, None
            frames = self.frames
            self.frames = []
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception as e:
                log("录音收尾出错", e)
        if not frames or time.time() - self.started < 0.25:
            return None
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="fishbuddy-")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(b"".join(frames))
        return path


# ---------------------------------------------------------------- 语音识别
class Speech:
    """SFSpeechRecognizer 包一层：录完的 wav → 一句话"""

    def __init__(self):
        from Speech import SFSpeechRecognizer
        self._SFSpeechRecognizer = SFSpeechRecognizer
        self.ready = False
        self.reason = "还没请求权限"

    def request_permission(self, done):
        from Speech import SFSpeechRecognizer
        SFSpeechRecognizer.requestAuthorization_(lambda status: done(int(status)))

    def transcribe(self, wav_path, timeout=20.0):
        from Speech import SFSpeechRecognizer, SFSpeechURLRecognitionRequest

        rec = SFSpeechRecognizer.alloc().initWithLocale_(
            NSLocale.localeWithLocaleIdentifier_("zh-CN")
        )
        if rec is None or not rec.isAvailable():
            return None, "这台机器的语音识别不可用"
        req = SFSpeechURLRecognitionRequest.alloc().initWithURL_(
            NSURL.fileURLWithPath_(wav_path)
        )
        req.setShouldReportPartialResults_(False)
        try:
            req.setRequiresOnDeviceRecognition_(True)
        except Exception:
            pass

        box = {}
        ev = threading.Event()

        def handler(result, error):
            if result is not None and result.bestTranscription() is not None:
                box["text"] = str(result.bestTranscription().formattedString())
                if result.isFinal():
                    ev.set()
            if error is not None:
                box["error"] = str(error.localizedDescription())
                ev.set()

        task = rec.recognitionTaskWithRequest_resultHandler_(req, handler)
        ev.wait(timeout)
        try:
            task.cancel()
        except Exception:
            pass
        if box.get("text"):
            return box["text"].strip(), None
        return None, box.get("error") or "没听清（超时）"


def placeholder_image():
    from AppKit import NSColor, NSImage, NSMakeRect

    img = NSImage.alloc().initWithSize_(NSMakeSize(BALL, BALL))
    img.lockFocus()
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.42, 0.72, 0.92).set()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(2, 2, BALL - 4, BALL - 4)).fill()
    img.unlockFocus()
    return img


class TTS:
    """她的回话念出来（系统语音合成，不用联网）"""

    def __init__(self):
        from AVFoundation import AVSpeechSynthesizer

        self.synth = AVSpeechSynthesizer.alloc().init()
        self.voice = None
        try:
            from AVFoundation import AVSpeechSynthesisVoice

            self.voice = AVSpeechSynthesisVoice.voiceWithLanguage_("zh-CN")
        except Exception:
            pass

    @objc.python_method
    def say(self, text):
        from AVFoundation import AVSpeechUtterance

        text = (text or "").strip()
        if not text:
            return
        try:
            utt = AVSpeechUtterance.speechUtteranceWithString_(text[:400])
            if self.voice is not None:
                utt.setVoice_(self.voice)
            utt.setRate_(0.5)
            self.synth.speakUtterance_(utt)
        except Exception as e:
            log("朗读失败", e)

    @objc.python_method
    def stop(self):
        try:
            self.synth.stopSpeakingAtBoundary_(0)
        except Exception:
            pass


class Hotkey:
    """⌥Space 按住说话（全局；要「辅助功能/输入监控」权限）"""

    def __init__(self, on_down, on_up):
        self.on_down = on_down
        self.on_up = on_up
        self.down = False
        self.monitors = []

    @objc.python_method
    def start(self):
        from AppKit import NSEvent, NSEventMaskKeyDown, NSEventMaskKeyUp

        if self.monitors:
            return True
        mask = NSEventMaskKeyDown | NSEventMaskKeyUp
        g = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, self._handle)
        loc = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, self._handle)
        self.monitors = [g, loc]
        return g is not None

    @objc.python_method
    def stop(self):
        from AppKit import NSEvent

        for m in self.monitors:
            try:
                NSEvent.removeMonitor_(m)
            except Exception:
                pass
        self.monitors = []

    @objc.python_method
    def _handle(self, ev):
        from AppKit import NSEventModifierFlagOption, NSEventTypeKeyDown, NSEventTypeKeyUp

        try:
            if ev.keyCode() != 49:  # space
                return ev
            if not (ev.modifierFlags() & NSEventModifierFlagOption):
                return ev
            if ev.type() == NSEventTypeKeyDown:
                if not self.down:
                    self.down = True
                    self.on_down()
            elif ev.type() == NSEventTypeKeyUp:
                if self.down:
                    self.down = False
                    self.on_up()
        except Exception as e:
            log("热键处理出错", e)
        return ev


def ax_trusted():
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


# ---------------------------------------------------------------- 气泡
class Bubble(NSObject):
    def initWithParent_(self, parent):
        self = objc.super(Bubble, self).init()
        if self is None:
            return None
        self.parent = parent
        self.win = None
        self.timer = None
        return self

    def hide_(self, timer):
        if self.win is not None:
            self.win.orderOut_(None)
            self.win = None
        self.timer = None

    @objc.python_method
    def show_text(self, text, seconds=6.0, error=False):
        if self.win is not None:
            self.win.orderOut_(None)
        pad = 16.0
        maxw = 320.0
        label = NSTextField.alloc().initWithFrame_(NSMakeRect(pad, pad, maxw, 40))
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.systemFontOfSize_(14))
        label.setTextColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.15, 1.0)
            if not error
            else NSColor.colorWithCalibratedRed_green_blue_alpha_(0.7, 0.12, 0.12, 1.0)
        )
        label.setUsesSingleLineMode_(False)
        label.setLineBreakMode_(0)
        label.cell().setWraps_(True)
        size = label.cell().cellSizeForBounds_(NSMakeRect(0, 0, maxw, 400))
        w = min(maxw, max(80.0, size.width)) + pad * 2
        h = min(400.0, size.height) + pad * 2
        label.setFrame_(NSMakeRect(pad, pad, w - pad * 2, h - pad * 2))

        win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, w, h),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setLevel_(4)
        win.setIgnoresMouseEvents_(True)
        win.setHasShadow_(True)
        win.setAlphaValue_(0.97)

        host = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        host.setWantsLayer_(True)
        rgba = (1.0, 0.93, 0.93, 0.97) if error else (0.99, 0.96, 0.93, 0.97)
        host.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba).CGColor()
        )
        host.layer().setCornerRadius_(16.0)
        host.addSubview_(label)
        win.setContentView_(host)

        o = self.parent.win.frameOrigin()
        x = o.x + BALL / 2 - w / 2
        y = o.y + BALL + 8
        win.setFrameOrigin_((x, y))
        win.orderFrontRegardless()
        self.win = win

        if self.timer is not None:
            try:
                self.timer.invalidate()
            except Exception:
                pass
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            seconds, self, "hide:", None, False
        )


# ---------------------------------------------------------------- 鲸鱼窗口
class BallView(NSView):
    """按住说话；拖动走位；右键菜单；双击打字"""

    def initWithParent_(self, parent):
        self = objc.super(BallView, self).initWithFrame_(
            NSMakeRect(0, 0, BALL, BALL)
        )
        if self is None:
            return None
        self.parent = parent
        self.press_origin = None
        self.win_origin = None
        self.dragging = False
        return self

    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        from AppKit import NSEvent

        self.start_mouse = NSEvent.mouseLocation()
        self.win_origin = self.parent.win.frameOrigin()
        self.moved = False
        if event.clickCount() == 2:
            self.parent.cancel_talk()
            self.parent.ask_text()
            return
        self.parent.begin_talk()

    def mouseDragged_(self, event):
        from AppKit import NSEvent

        cur = NSEvent.mouseLocation()
        dx = cur.x - self.start_mouse.x
        dy = cur.y - self.start_mouse.y
        if abs(dx) > 5 or abs(dy) > 5:
            if not self.moved:
                self.moved = True
                self.parent.cancel_talk()
            self.parent.win.setFrameOrigin_((self.win_origin.x + dx, self.win_origin.y + dy))

    def mouseUp_(self, event):
        if not self.moved:
            self.parent.end_talk()

    def rightMouseDown_(self, event):
        self.parent.show_menu(event)

    def drawRect_(self, rect):
        # 背景全透明：鲸鱼 PNG 自己带透明通道
        pass


class Whale(NSObject):
    def init(self):
        self = objc.super(Whale, self).init()
        if self is None:
            return None
        self.win = None
        self.view = None
        self.rec = Recorder()
        self.speech = None
        self.listening = False
        self.busy = False
        self.status_item = None
        self.state = "idle"   # idle | listen | think
        self.watching = False
        self.sent_frames = 0
        self.strip = None
        self.strip_label = None
        self.settings = load_settings()
        self.watch_interval = float(self.settings.get("陪看间隔") or 20)
        self.tts = None
        self.hotkey = None
        return self

    # ---------- 窗口 ----------
    @objc.python_method
    def build(self):
        img = None
        for cand in ASSET_CANDIDATES:
            if os.path.exists(cand):
                img = NSImage.alloc().initWithContentsOfFile_(cand)
                if img is not None:
                    break
        if img is None:
            # 没图也能跑：画一个圆底 + 🐋，方便你自己换图
            img = placeholder_image()
        frame = self.ball_frame_origin()
        self.win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(frame.x, frame.y, BALL, BALL),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        self.win.setOpaque_(False)
        self.win.setBackgroundColor_(NSColor.clearColor())
        self.win.setLevel_(3)
        self.win.setHasShadow_(False)
        self.win.setMovableByWindowBackground_(False)
        self.win.setIgnoresMouseEvents_(False)
        self.win.setHidesOnDeactivate_(False)

        host = BallView.alloc().initWithParent_(self)
        self.view = host
        self.iv = NSImageView.alloc().initWithFrame_(NSMakeRect(0, 0, BALL, BALL))
        self.iv.setImage_(img)
        self.iv.setImageScaling_(3)  # 等比缩放
        self.iv.setEditable_(False)
        host.addSubview_(self.iv)
        self.win.setContentView_(host)
        self.win.orderFrontRegardless()
        self.win.setFrameOrigin_((frame.x, frame.y))
        self.build_strip()

    @objc.python_method
    def ball_frame_origin(self):
        try:
            import AppKit

            scr = AppKit.NSScreen.mainScreen().visibleFrame()
            return NSMakeRect(scr.size.width - BALL - 60, scr.size.height - BALL - 120, BALL, BALL).origin
        except Exception:
            return NSMakeRect(100, 100, BALL, BALL).origin



    # ---------- 说话 ----------
    @objc.python_method
    def begin_talk(self):
        if self.busy or self.listening:
            return
        if not self.speech_ok():
            return
        try:
            self.rec.start()
            self.listening = True
            self.set_state("listen")
            self.bubble.show_text("听着呢…", 30)
        except Exception as e:
            log("开麦失败", e)
            self.bubble.show_text(f"开不了麦克风：{e}", 5, error=True)

    @objc.python_method
    def cancel_talk(self):
        if not self.listening:
            return
        self.listening = False
        self.rec.stop()
        self.set_state("idle")
        self.bubble.show_text("拖动中…", 1.2)

    @objc.python_method
    def end_talk(self):
        if not self.listening:
            return
        self.listening = False
        self.set_state("think")
        wav = self.rec.stop()
        if not wav:
            self.set_state("idle")
            self.bubble.show_text("太短了，按住多说一会儿～", 3)
            return
        threading.Thread(target=self._recognize, args=(wav,), daemon=True).start()

    @objc.python_method
    def _recognize(self, wav):
        txt, err = self.speech.transcribe(wav)
        try:
            os.unlink(wav)
        except Exception:
            pass
        if not txt:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "uiError:", err or "没听清", False
            )
            return
        self.performSelectorOnMainThread_withObject_waitUntilDone_("uiHeard:", txt, False)

    def uiHeard_(self, txt):
        self.bubble.show_text(f"你说：{txt}", 2.5)
        self.send(txt)

    def uiError_(self, err):
        self.set_state("idle")
        self.bubble.show_text(str(err), 6, error=True)

    def uiInfo_(self, msg):
        self.set_state("idle")
        self.bubble.show_text(str(msg), 4)

    @objc.python_method
    def send(self, text):
        cfg = read_binding()
        if not str(cfg.get("会话") or "").strip():
            self.set_state("idle")
            self.bubble.show_text("DSH 那边还没绑会话：设置 → 鱼搭子 → 送到哪一间", 6, error=True)
            return

        def run():
            try:
                body = json.dumps({"text": text}).encode("utf-8")
                req = urllib.request.Request(
                    SEND_URL, data=body, headers={"content-type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    j = json.loads(r.read().decode("utf-8"))
                ok = bool(j.get("ok"))
                msg = j.get("说") or ("送进去了" if ok else "没送进去")
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "uiState:", "ok" if ok else msg, False
                )
            except Exception as e:
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "uiState:", f"连不上 DSH（8777）：{e}", False
                )

        threading.Thread(target=run, daemon=True).start()

    def uiState_(self, msg):
        self.set_state("idle")
        if msg != "ok":
            self.bubble.show_text(str(msg), 6, error=True)

    def speak_(self, text):
        """她说话了：气泡 + （可选）念出来"""
        if not text:
            return
        self.set_state("idle")
        self.bubble.show_text(text, 10)
        if self.settings.get("朗读") and self.tts is not None:
            self.tts.say(text)

    @objc.python_method
    def ask_text(self):
        from AppKit import NSAlert

        a = NSAlert.alloc().init()
        a.setMessageText_("打字说")
        a.setInformativeText_("先不开口也行，打一句送给她")
        a.addButtonWithTitle_("发送")
        a.addButtonWithTitle_("取消")
        f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, 24))
        a.setAccessoryView_(f)
        a.window().makeFirstResponder_(f)
        if a.runModal() == 1000:
            t = str(f.stringValue()).strip()
            if t:
                self.bubble.show_text(f"你说：{t}", 2.0)
                self.send(t)

    # ---------- 陪看 ----------
    @objc.python_method
    def build_strip(self):
        w, h = 300.0, 34.0
        try:
            from AppKit import NSScreen

            vis = NSScreen.mainScreen().visibleFrame()
            x = vis.origin.x + vis.size.width - w - 28
            y = vis.origin.y + 24
        except Exception:
            x, y = 200.0, 60.0
        self.strip = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        self.strip.setOpaque_(False)
        self.strip.setBackgroundColor_(NSColor.clearColor())
        self.strip.setLevel_(3)
        self.strip.setIgnoresMouseEvents_(True)
        self.strip.setHasShadow_(True)
        host = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        host.setWantsLayer_(True)
        host.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.1, 0.14, 0.72).CGColor()
        )
        host.layer().setCornerRadius_(12.0)
        lab = NSTextField.alloc().initWithFrame_(NSMakeRect(14, 8, w - 28, 18))
        lab.setBezeled_(False)
        lab.setDrawsBackground_(False)
        lab.setEditable_(False)
        lab.setSelectable_(False)
        lab.setFont_(NSFont.systemFontOfSize_(12))
        lab.setTextColor_(NSColor.whiteColor())
        lab.setStringValue_("陪看 · 还没开始")
        host.addSubview_(lab)
        self.strip.setContentView_(host)
        self.strip_label = lab
        self.strip.setAlphaValue_(0.0)
        self.strip.orderFrontRegardless()

    @objc.python_method
    def update_strip(self, text):
        try:
            if self.strip_label is not None:
                self.strip_label.setStringValue_(text)
            if self.strip is not None:
                self.strip.setAlphaValue_(0.95 if self.watching else 0.0)
        except Exception:
            pass

    @objc.python_method
    def toggle_watch(self):
        self.watching = not self.watching
        if self.watching:
            self.update_strip("陪看中 · 每 %d 秒看一眼" % int(self.watch_interval))
            threading.Thread(target=self.watch_loop, daemon=True).start()
            self.bubble.show_text("陪看开了：每 20 秒截一张，攒着等说话时一起给她看", 4)
        else:
            self.update_strip("陪看 · 已停")
            self.bubble.show_text("陪看停了", 2)

    @objc.python_method
    def watch_loop(self):
        while self.watching:
            ok, msg = self.send_frame(False, "陪看")
            if not ok:
                self.watching = False
                self.performSelectorOnMainThread_withObject_waitUntilDone_("uiError:", msg, False)
                self.update_strip("陪看 · 出错了")
                return
            self.sent_frames += 1
            self.update_strip(
                "陪看中 ● 已送 %d 张 · %s" % (self.sent_frames, time.strftime("%H:%M:%S"))
            )
            for _ in range(int(self.watch_interval * 10)):
                if not self.watching:
                    return
                time.sleep(0.1)

    @objc.python_method
    def send_frame(self, immediate, source, quiet=True):
        b64, err = capture_screen()
        if not b64:
            return False, "截屏失败：%s（系统设置 → 隐私与安全性 → 屏幕录制，把「大肥鱼」勾上，然后退出重开）" % err
        body = json.dumps(
            {
                "图片": b64,
                "立即": 1 if immediate else 0,
                "存档": 0 if immediate else 1,
                "来源": source,
            }
        ).encode("utf-8")
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8777/hands/frame",
                data=body,
                headers={"content-type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.loads(r.read().decode("utf-8"))
            if not j.get("ok"):
                return False, str(j.get("说") or "插件没收")
            if not quiet:
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "uiState:", str(j.get("说") or "送过去了"), False
                )
            return True, str(j.get("说") or "")
        except Exception as e:
            return False, "连不上 DSH（8777）：%s" % e

    @objc.python_method
    def look_now(self):
        self.bubble.show_text("拍一张给她看…", 2)

        def run():
            ok, msg = self.send_frame(True, "陪看")
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "uiInfo:", ("拍好了，等她说话" if ok else msg), False
            )

        threading.Thread(target=run, daemon=True).start()

    def watchMenu_(self, sender):
        self.toggle_watch()
        sender.setTitle_("陪看（%s）" % ("开" if self.watching else "关"))

    def lookMenu_(self, sender):
        self.look_now()

    def speakMenu_(self, sender):
        self.settings["朗读"] = not self.settings.get("朗读")
        save_settings(self.settings)
        sender.setTitle_("念出来（%s）" % ("开" if self.settings["朗读"] else "关"))
        if not self.settings["朗读"] and self.tts is not None:
            self.tts.stop()

    def hotkeyMenu_(self, sender):
        self.settings["热键"] = not self.settings.get("热键")
        save_settings(self.settings)
        if self.settings["热键"]:
            ok = self.hotkey.start() if self.hotkey is not None else False
            self.bubble.show_text(
                "⌥Space 按住说话：开了" if ok else "热键没起来——去系统设置给「辅助功能」权限",
                5,
                error=not ok,
            )
        else:
            if self.hotkey is not None:
                self.hotkey.stop()
            self.bubble.show_text("全局热键关了", 2)
        sender.setTitle_("全局热键 ⌥Space（%s）" % ("开" if self.settings["热键"] else "关"))

    def openAccessibility_(self, sender):
        from AppKit import NSURL, NSWorkspace

        NSWorkspace.sharedWorkspace().openURL_(
            NSURL.URLWithString_(
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            )
        )
        self.bubble.show_text("把「大肥鱼」勾上，然后重开挂件", 6)

    def openScreenSettings_(self, sender):
        from AppKit import NSURL, NSWorkspace

        url = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
        self.bubble.show_text("把「大肥鱼」勾上，然后退出重开挂件", 6)

    # ---------- 状态/外观 ----------
    @objc.python_method
    def set_state(self, s):
        self.state = s
        alpha = {"idle": 1.0, "listen": 0.85, "think": 0.9}.get(s, 1.0)
        try:
            self.win.setAlphaValue_(alpha)
            if s == "listen":
                self.iv.setFrameSize_(NSMakeSize(BALL * 1.08, BALL * 1.08))
                self.iv.setFrameOrigin_((-BALL * 0.04, -BALL * 0.04))
            else:
                self.iv.setFrame_(NSMakeRect(0, 0, BALL, BALL))
        except Exception:
            pass

    @objc.python_method
    def speech_ok(self):
        if self.speech is None:
            self.bubble.show_text("语音模块没准备好", 4, error=True)
            return False
        return True

    def show_menu(self, event):
        m = NSMenu.alloc().init()
        itw = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "陪看（%s）" % ("开" if self.watching else "关"), "watchMenu:", ""
        )
        itw.setTarget_(self)
        m.addItem_(itw)
        itl = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("让她看一眼", "lookMenu:", "")
        itl.setTarget_(self)
        m.addItem_(itl)
        its = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打开屏幕录制设置", "openScreenSettings:", "")
        its.setTarget_(self)
        m.addItem_(its)
        m.addItem_(NSMenuItem.separatorItem())
        itv = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "念出来（%s）" % ("开" if self.settings.get("朗读") else "关"), "speakMenu:", ""
        )
        itv.setTarget_(self)
        m.addItem_(itv)
        ith = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "全局热键 ⌥Space（%s）" % ("开" if self.settings.get("热键") else "关"), "hotkeyMenu:", ""
        )
        ith.setTarget_(self)
        m.addItem_(ith)
        ita = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打开辅助功能设置", "openAccessibility:", "")
        ita.setTarget_(self)
        m.addItem_(ita)
        m.addItem_(NSMenuItem.separatorItem())
        it1 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打个招呼", "ping:", "")
        it1.setTarget_(self)
        m.addItem_(it1)
        it2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quit:", "q")
        it2.setTarget_(self)
        m.addItem_(it2)
        NSMenu.popUpContextMenu_withEvent_forView_(m, event, self.view)

    def ping_(self, sender):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8777/hands/ping", timeout=4) as r:
                j = json.loads(r.read().decode("utf-8"))
            self.bubble.show_text("DSH：%s" % (j.get("说") or "在"), 4)
        except Exception as e:
            self.bubble.show_text(f"DSH 没应答：{e}", 5, error=True)

    def quit_(self, sender):
        NSApplication.sharedApplication().terminate_(None)


# ---------------------------------------------------------------- 回话服务
class ReplyServer(ThreadingHTTPServer):
    daemon_threads = True


def start_reply_server(on_text):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._send({"ok": True, "说": "鱼搭子在"})

        def do_POST(self):
            n = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                j = json.loads(raw.decode("utf-8"))
            except Exception:
                j = {}
            text = str(j.get("text") or j.get("正文") or "").strip()
            if text:
                on_text(text)
            self._send({"ok": True})

    srv = ReplyServer(("127.0.0.1", REPLY_PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------- 启动
def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    whale = Whale.alloc().init()
    whale.build()
    whale.bubble = Bubble.alloc().initWithParent_(whale)

    speech = Speech()
    whale.speech = speech

    def on_auth(status):
        try:
            with open(os.path.join(HERE, "auth.log"), "a", encoding="utf-8") as f:
                f.write("%s auth=%s\n" % (time.strftime("%H:%M:%S"), status))
        except Exception:
            pass
        # 3 = authorized
        if status == 3:
            speech.ready = True
            whale.performSelectorOnMainThread_withObject_waitUntilDone_(
                "uiState:", "ok", False
            )
        else:
            speech.reason = f"语音识别权限没给（status={status}）"
            whale.performSelectorOnMainThread_withObject_waitUntilDone_(
                "uiError:", "语音识别没授权：系统设置 → 隐私与安全性 → 语音识别，把「大肥鱼」打开", False
            )

    speech.request_permission(on_auth)

    start_reply_server(lambda t: whale.performSelectorOnMainThread_withObject_waitUntilDone_("speak:", t, False))

    whale.tts = TTS()
    whale.hotkey = Hotkey(whale.begin_talk, whale.end_talk)
    if whale.settings.get("热键"):
        if not whale.hotkey.start():
            log("全局热键没起来（缺辅助功能权限），只能按住鲸鱼说话")
        elif not ax_trusted():
            log("热键在跑，但系统可能还没给「辅助功能」权限")

    # 状态栏图标，方便退出
    item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    item.button().setTitle_("🐋")
    menu = NSMenu.alloc().init()
    mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quit:", "q")
    mi.setTarget_(whale)
    menu.addItem_(mi)
    item.setMenu_(menu)
    whale.status_item = item

    if os.environ.get("FISH_TEST_SHOT"):
        def run_shot():
            time.sleep(1.5)
            b64, err = capture_screen()
            with open(os.path.join(HERE, "shot.log"), "a", encoding="utf-8") as f:
                f.write("%s SHOT bytes=%s err=%r\n" % (time.strftime("%H:%M:%S"), len(b64) if b64 else 0, err))
        threading.Thread(target=run_shot, daemon=True).start()

    if os.environ.get("FISH_TEST_MIC"):
        def run_mic():
            time.sleep(1.5)
            try:
                r = Recorder()
                r.start()
                time.sleep(1.5)
                wav = r.stop()
                import wave as _w
                n = 0
                if wav:
                    with _w.open(wav) as w:
                        n = w.getnframes()
                with open(os.path.join(HERE, "mic.log"), "a", encoding="utf-8") as f:
                    f.write("%s MIC frames=%s wav=%r\n" % (time.strftime("%H:%M:%S"), n, wav))
            except Exception as e:
                with open(os.path.join(HERE, "mic.log"), "a", encoding="utf-8") as f:
                    f.write("%s MIC ERR %r\n" % (time.strftime("%H:%M:%S"), e))
        threading.Thread(target=run_mic, daemon=True).start()

    test_wav = os.environ.get("FISH_TEST_WAV")
    if test_wav:
        def run_test():
            time.sleep(2.5)
            txt, err = speech.transcribe(test_wav)
            with open(os.path.join(HERE, "asr.log"), "a", encoding="utf-8") as f:
                f.write("%s ASR=%r ERR=%r\n" % (time.strftime("%H:%M:%S"), txt, err))
            os.environ.pop("FISH_TEST_WAV", None)
        threading.Thread(target=run_test, daemon=True).start()

    log("起来了：8778 收话，8777 送话")
    bubble_tip = "按住鲸鱼说话 · 拖动走位 · 双击打字"
    whale.bubble.show_text(bubble_tip, 5)
    app.run()


if __name__ == "__main__":
    main()
