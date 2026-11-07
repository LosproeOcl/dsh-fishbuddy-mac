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
    NSButton,
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
    NSPopUpButton,
    NSSegmentedControl,
    NSSlider,
    NSStatusBar,
    NSStepper,
    NSTextField,
    NSVariableStatusItemLength,
    NSView,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
)
from Foundation import NSURL, NSLocale, NSTimer

SEND_URL = "http://127.0.0.1:8777/hands/say"
REPLY_PORT = 8778
DSH_HOME = os.environ.get("DSH_HOME") or os.path.expanduser("~/.dsh")
CONFIG_PATH = os.path.join(DSH_HOME, "fish-buddy-config.json")
SETTINGS_PATH = os.path.join(DSH_HOME, "fishbuddy-mac.json")
DEFAULT_SETTINGS = {
    "挂件": True,          # 桌面上有没有那只鲸鱼（关掉只留菜单栏）
    "形象": "image",       # image = 素材形象；minimal = 极简圆点
    "朗读": True,
    "热键": True,
    "热键表": {
        "说话": [49, 1 << 19],    # ⌥Space（按住）
        "陪看": [35, 1 << 19],    # ⌥P（切换）
        "看一眼": [37, 1 << 19],  # ⌥L（按一下）
        "设置": [1, 1 << 19],     # ⌥S（打开设置）
    },
    "尺寸": 132,          # 图标边长（像素）
    "弹幕": True,         # 她的回话同时以弹幕形式滑过屏幕
    "弹幕字号": 30,       # 弹幕字号（px）
    "弹幕字体": "",       # 空 = 系统粗体；否则是系统字体族名
    "识别提示": "",       # 语音识别的上下文词（逗号分隔），提高专有名词准确率
    "音色": "system",     # system = 系统音色；edge = 晓晓（在线，更像真人）
    "陪看间隔": 20,
}

MOD_MASK = (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)

# 热键动作：名字 → 说明（顺序就是设置窗口里的顺序）
HOTKEY_ACTIONS = [
    ("说话", "按住说话（松开发送）"),
    ("陪看", "陪看 开 / 关"),
    ("看一眼", "让她立刻看一眼"),
    ("设置", "打开挂件设置"),
]

# 按 Apple 的书写习惯排：⌃⌥⇧⌘
MOD_NAMES = [
    (1 << 18, "⌃"), (1 << 19, "⌥"), (1 << 17, "⇧"), (1 << 20, "⌘"),
]

KEY_NAMES = {
    49: "Space", 48: "Tab", 36: "Return", 53: "Esc", 51: "Delete",
    126: "↑", 125: "↓", 123: "←", 124: "→",
    18: "1", 19: "2", 20: "3", 21: "4", 23: "5", 22: "6",
    26: "7", 28: "8", 25: "9", 29: "0",
    # 字母
    0: "A", 11: "B", 8: "C", 2: "D", 14: "E", 3: "F", 5: "G", 4: "H",
    34: "I", 38: "J", 40: "K", 37: "L", 46: "M", 45: "N", 31: "O", 35: "P",
    12: "Q", 15: "R", 1: "S", 17: "T", 32: "U", 9: "V", 13: "W", 7: "X",
    16: "Y", 6: "Z",
    # 符号
    27: "-", 24: "=", 33: "[", 30: "]", 41: ";", 39: "'", 43: ",",
    47: ".", 44: "/", 42: "\\", 50: "`", 10: "§",
    122: "F1", 120: "F2", 99: "F3", 118: "F4", 96: "F5", 97: "F6",
    98: "F7", 100: "F8", 101: "F9", 109: "F10", 103: "F11", 111: "F12",
}

# macOS 自带的常用快捷键——撞上就提醒（查不到系统全表，这里只列最常撞的）
SYSTEM_HOTKEYS = {
    (49, 1 << 20): "Spotlight 搜索",
    (49, 1 << 18): "切换输入法",
    (49, (1 << 20) | (1 << 19)): "Finder 搜索",
    (48, 1 << 20): "切换 App",
    (12, 1 << 20): "退出 App",
    (20, (1 << 20) | (1 << 17)): "截屏（全屏）",
    (21, (1 << 20) | (1 << 17)): "截屏（选区）",
    (23, (1 << 20) | (1 << 17)): "截屏与录屏",
    (126, 1 << 18): "调度中心",
    (125, 1 << 18): "App 窗口",
    (3, 1 << 20): "Finder",
    (2, 1 << 20): "Finder",
}


def key_name(code, mask):
    mods = "".join(name for bit, name in MOD_NAMES if mask & bit)
    return mods + KEY_NAMES.get(code, "键%d" % code)


def hotkey_conflict(code, mask, table=None, skip=None):
    """返回冲突说明；没问题返回 None。

    table: 当前热键表（name -> [code, mask]），用来查「和别的动作撞了」
    skip:  正在改的那个动作名（它自己不算冲突）
    """
    if not (mask & ((1 << 20) | (1 << 19) | (1 << 18))):
        return "要带 ⌘ / ⌥ / ⌃ 其中一个，不然会抢走打字"
    sys_hit = SYSTEM_HOTKEYS.get((code, mask))
    if sys_hit:
        return "和系统快捷键「%s」撞了" % sys_hit
    for name, combo in (table or {}).items():
        if name == skip:
            continue
        try:
            c, m = int(combo[0]), int(combo[1])
        except Exception:
            continue
        if c == code and (m & MOD_MASK) == mask:
            return "和「%s」用了同一个组合" % name
    return None
HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_CANDIDATES = [
    os.path.join(HERE, "assets", "whale.png"),
    os.path.join(HERE, "assets", "鱼搭子.png"),  # 本地自用
]

VERSION = "0.10.5"
BALL = 132          # 鲸鱼直径
SAMPLE_RATE = 16000
MAX_RECORD = 30.0


def log(*a):
    line = "[fish] " + " ".join(str(x) for x in a)
    print(line, flush=True)
    try:
        with open(os.path.join(HERE, "fishbuddy.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), line))
    except Exception:
        pass


def mic_status():
    """0 未决定 / 1 受限 / 2 拒绝 / 3 已授权（TCC）"""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        return int(AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio))
    except Exception:
        return -1


def request_mic():
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, lambda ok: None)
    except Exception as e:
        log("申请麦克风失败", e)


def system_font_families():
    """系统里所有字体族（去重、排序）—— 下拉列表用"""
    try:
        from AppKit import NSFontManager

        fams = [str(x) for x in (NSFontManager.sharedFontManager().availableFontFamilies() or [])]
        return sorted({f.strip() for f in fams if f and f.strip()})
    except Exception:
        return ["PingFang SC"]


def input_devices():
    """[(index, name), …] —— 所有能录的设备"""
    out = []
    try:
        import sounddevice as sd

        for i, d in enumerate(sd.query_devices()):
            if int(d.get("max_input_channels") or 0) > 0:
                out.append((i, str(d.get("name") or ("设备 %d" % i))))
    except Exception:
        pass
    return out


def input_device_name():
    try:
        import sounddevice as sd

        idx = sd.default.device[0]
        info = sd.query_devices(idx)
        return str(info.get("name") or "")
    except Exception:
        return ""


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
    """插件那半边绑了哪间会话（只读，用来提前提示没绑）"""
    for path in (os.path.join(DSH_HOME, "fishbuddy-mac-plugin.json"), CONFIG_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
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
    def __init__(self, device=None):
        self.device = device
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

        kwargs = dict(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024, callback=cb
        )
        if self.device is not None:
            kwargs["device"] = self.device
        self.stream = sd.InputStream(**kwargs)
        self.stream.start()

    def stop(self):
        """返回 (wav 路径, 峰值)；没录到东西返回 (None, 0)"""
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
        if not frames or time.time() - self.started < 0.2:
            return None, 0.0
        raw = b"".join(frames)
        peak = 0.0
        if raw:
            import numpy as np

            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            peak = float(abs(a).max()) if a.size else 0.0
            loud = np.where(np.abs(a) > max(150.0, peak * 0.06))[0]
            if loud.size:
                pad = int(SAMPLE_RATE * 0.15)
                a = a[max(0, int(loud[0]) - pad):min(a.size, int(loud[-1]) + pad)]
            cur = float(abs(a).max()) if a.size else 0.0
            gain = 1.0
            if 0 < cur < 26000:
                gain = min(16.0, 26000.0 / max(cur, 1.0))
            if gain > 1.0:
                a = np.clip(a * gain, -32768, 32767)
            raw = a.astype(np.int16).tobytes()
            log("录音：峰值 %.0f，增益 %.1fx，%.2fs" % (peak, gain, a.size / SAMPLE_RATE))
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="fishbuddy-")
        os.close(fd)
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(raw)
        return path, peak

def ocr_screen_text(pil_img, box_hint=0.30):
    """截图底部一块做 OCR（陪看抽台词）。返回 [行, …]"""
    try:
        import io

        import Quartz
        import Vision
        from Foundation import NSData

        w, h = pil_img.size
        crop = pil_img.crop((0, int(h * (1 - box_hint)), w, h)).convert("RGB")
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        data = NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
        src = Quartz.CGImageSourceCreateWithData(data, None)
        if src is None:
            return []
        cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        if cg is None:
            return []
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(0)  # accurate
        try:
            req.setRecognitionLanguages_(["zh-Hans", "en-US"])
        except Exception:
            pass
        req.setUsesLanguageCorrection_(True)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
        handler.performRequests_error_([req], None)
        out = []
        for obs in req.results() or []:
            cands = obs.topCandidates_(1)
            if cands and len(cands):
                t = str(cands[0].string()).strip()
                if t:
                    out.append(t)
        return out[-4:]
    except Exception as e:
        log("OCR 失败", e)
        return []


# ---------------------------------------------------------------- 弹幕
class Danmaku(NSObject):
    """把她的回话当弹幕从屏幕右边滑过去（点击穿透）"""

    def initWithParent_(self, parent):
        self = objc.super(Danmaku, self).init()
        if self is None:
            return None
        self.parent = parent
        self.win = None
        self.label = None
        self.step = 0.0
        self.timer = None
        return self

    def fly_(self, timer):
        if self.win is None:
            try:
                timer.invalidate()
            except Exception:
                pass
            return
        f = self.win.frame()
        x = f.origin.x - self.step
        self.win.setFrameOrigin_((x, f.origin.y))
        if x + f.size.width < 0:
            self.win.orderOut_(None)
            self.win = None
            self.timer = None
            try:
                timer.invalidate()
            except Exception:
                pass

    @objc.python_method
    def show_text(self, text):
        """一条弹幕：窗口宽度按文字实际宽度算，长句也能整段滑完（不被截断）"""
        from AppKit import NSColor, NSFont, NSScreen, NSTextField

        try:
            text = (text or "").strip()
            if not text:
                return
            scr = NSScreen.mainScreen().frame()
            sw = scr.size.width
            size = float(self.parent.settings.get("弹幕字号") or 30)
            fam = str(self.parent.settings.get("弹幕字体") or "")
            font = None
            try:
                if fam:
                    from AppKit import NSFontManager

                    font = NSFontManager.sharedFontManager().fontWithFamily_traits_weight_size_(
                        fam, 0, 5, size
                    )
            except Exception:
                font = None
            font = font or NSFont.boldSystemFontOfSize_(size)

            text = text[:120]   # 再长就不是弹幕了

            width = 0.0
            try:
                from Foundation import NSString

                width = float(
                    NSString.stringWithString_(text)
                    .sizeWithAttributes_({"NSFont": font})
                    .width
                )
            except Exception:
                width = len(text) * size
            pad = 48.0
            win_w = max(sw, width + pad * 2)
            h = max(54.0, size * 1.8)

            self.label = NSTextField.alloc().initWithFrame_(
                NSMakeRect(pad, (h - size * 1.6) / 2, width + pad, size * 1.6)
            )
            self.label.setStringValue_(text)
            self.label.setBezeled_(False)
            self.label.setDrawsBackground_(False)
            self.label.setEditable_(False)
            self.label.setSelectable_(False)
            self.label.setFont_(font)
            self.label.setTextColor_(NSColor.whiteColor())
            self.label.setAlignment_(0)
            self.label.setUsesSingleLineMode_(True)
            self.label.setLineBreakMode_(2)   # 不换行、不截断

            if self.win is None:
                self.win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                    NSMakeRect(sw, scr.size.height * 0.72, win_w, h),
                    NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                    NSBackingStoreBuffered,
                    False,
                )
                self.win.setOpaque_(False)
                self.win.setBackgroundColor_(NSColor.clearColor())
                self.win.setLevel_(5)
                self.win.setIgnoresMouseEvents_(True)
            self.win.setContentView_(self.label)
            self.win.setFrame_display_(
                NSMakeRect(sw, scr.size.height * 0.72, win_w, h), False
            )
            self.win.orderFrontRegardless()

            if self.timer is not None:
                try:
                    self.timer.invalidate()
                except Exception:
                    pass
            # 恒定速度 200px/s：长句慢一点、短句快一点，都读得完
            self.step = 200.0 / 30.0
            self.timer = (
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    1.0 / 30.0, self, "fly:", None, True
                )
            )
        except Exception as e:
            log("弹幕失败", e)


# ---------------------------------------------------------------- 语音识别
class Speech:
    """SFSpeechRecognizer 包一层：录完的 wav → 一句话"""

    def __init__(self, hint_words=""):
        from Speech import SFSpeechRecognizer
        self.hint_words = hint_words
        self._SFSpeechRecognizer = SFSpeechRecognizer
        self.ready = False
        self.reason = "还没请求权限"

    def request_permission(self, done):
        from Speech import SFSpeechRecognizer
        SFSpeechRecognizer.requestAuthorization_(lambda status: done(int(status)))

    def transcribe(self, wav_path, timeout=25.0):
        """先试离线识别；没结果就退回在线识别。返回 (文字, 错误)"""
        txt, err = self._recognize(wav_path, on_device=True, timeout=timeout)
        if txt:
            return txt, None
        log("离线识别没结果（%s），改用在线识别再试" % (err or "无文本"))
        txt2, err2 = self._recognize(wav_path, on_device=False, timeout=timeout)
        if txt2:
            return txt2, None
        return None, err2 or err

    def _recognize(self, wav_path, on_device, timeout):
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
            hint = str((self.hint_words or "")).strip()
            words = [w.strip() for w in hint.replace("，", ",").split(",") if w.strip()]
            if words:
                req.setContextualStrings_(words[:50])
        except Exception:
            pass
        try:
            req.setRequiresOnDeviceRecognition_(bool(on_device))
        except Exception:
            pass

        box = {}
        ev = threading.Event()

        def handler(result, error):
            if result is not None and result.bestTranscription() is not None:
                t = str(result.bestTranscription().formattedString()).strip()
                if t:
                    box["text"] = t
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
            return box["text"], None
        return None, box.get("error") or "没听清（超时）"

def frost_view(rect, radius=16.0):
    """磨砂玻璃层（macOS 的 NSVisualEffectView）"""
    try:
        eff = NSVisualEffectView.alloc().initWithFrame_(rect)
        eff.setMaterial_(3)          # HUDWindow
        eff.setBlendingMode_(0)      # behindWindow
        eff.setState_(1)             # active
        eff.setWantsLayer_(True)
        eff.layer().setCornerRadius_(radius)
        eff.layer().setMasksToBounds_(True)
        return eff
    except Exception:
        return None


def placeholder_image():
    from AppKit import NSColor, NSImage, NSMakeRect

    img = NSImage.alloc().initWithSize_(NSMakeSize(BALL, BALL))
    img.lockFocus()
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.42, 0.72, 0.92).set()
    NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(2, 2, BALL - 4, BALL - 4)).fill()
    img.unlockFocus()
    return img


class TTS:
    """念她的回话。两档：
       system —— 系统语音（挑质量最高的中文音色）
       edge   —— 微软 Edge 的在线神经音色（晓晓），更像真人；要联网
    """

    def __init__(self):
        from AVFoundation import AVSpeechSynthesizer

        self.synth = AVSpeechSynthesizer.alloc().init()
        self.voice = self._best_voice()
        self.proc = None

    @objc.python_method
    def _best_voice(self):
        """系统里质量最高的中文音色（premium > enhanced > default）"""
        try:
            from AVFoundation import AVSpeechSynthesisVoice

            best, best_q = None, -1
            for v in AVSpeechSynthesisVoice.speechVoices() or []:
                lang = str(v.language() or "")
                if not lang.startswith("zh"):
                    continue
                q = int(v.quality())
                if q > best_q:
                    best, best_q = v, q
            if best is not None:
                log("系统音色：%s（quality=%d）" % (best.name(), best_q))
            return best
        except Exception as e:
            log("挑音色失败", e)
            return None

    @objc.python_method
    def say(self, text, mode="system", blocking=False):
        text = (text or "").strip()
        if not text:
            return
        if mode == "edge":
            ok = self._say_edge(text, blocking)
            if ok:
                return
            log("edge 音色不可用，退回系统音色")
        self._say_system(text)

    @objc.python_method
    def _say_system(self, text):
        from AVFoundation import AVSpeechUtterance

        try:
            utt = AVSpeechUtterance.speechUtteranceWithString_(text[:400])
            if self.voice is not None:
                utt.setVoice_(self.voice)
            utt.setRate_(0.48)   # 慢一点点，更像说话
            utt.setPitchMultiplier_(1.02)
            self.synth.speakUtterance_(utt)
        except Exception as e:
            log("朗读失败", e)

    @objc.python_method
    def _say_edge(self, text, blocking):
        """edge-tts 合成 + afplay 播放（blocking=True 时等它播完）"""
        import shutil
        import subprocess
        import sys
        import tempfile

        if shutil.which("edge-tts") is None and not _has_module("edge_tts"):
            return False
        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="fishbuddy-tts-")
        os.close(fd)
        try:
            cmd = [sys.executable, "-m", "edge_tts", "--voice", "zh-CN-XiaoxiaoNeural",
                   "--text", text[:400], "--write-media", path]
            r = subprocess.run(cmd, capture_output=True, timeout=20)
            if r.returncode != 0 or os.path.getsize(path) < 800:
                return False
            p = subprocess.Popen(["afplay", path])
            self.proc = p
            if blocking:
                p.wait()
                try:
                    os.unlink(path)
                except Exception:
                    pass
            else:
                def clean():
                    p.wait()
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
                threading.Thread(target=clean, daemon=True).start()
            return True
        except Exception as e:
            log("edge 朗读失败", e)
            try:
                os.unlink(path)
            except Exception:
                pass
            return False

    @objc.python_method
    def is_speaking(self):
        try:
            if self.proc is not None and self.proc.poll() is None:
                return True
        except Exception:
            pass
        try:
            return bool(self.synth.isSpeaking())
        except Exception:
            return False

    @objc.python_method
    def stop(self):
        try:
            self.synth.stopSpeakingAtBoundary_(0)
        except Exception:
            pass
        try:
            if self.proc is not None:
                self.proc.terminate()
                self.proc = None
        except Exception:
            pass


def _has_module(name):
    import importlib.util

    return importlib.util.find_spec(name) is not None


class Hotkeys:
    """多动作全局热键：说话（按住）/ 陪看（切换）/ 看一眼 / 设置。

    绑定存在 settings["热键表"]，形如 {"说话": [49, 524288]}。
    需要「辅助功能」权限，否则全局那几个键收不到。
    """

    def __init__(self, speak_down, speak_up, fire, table):
        self.speak_down = speak_down
        self.speak_up = speak_up
        self.fire = fire            # fire(action_name)
        self.table = table          # callable -> dict
        self.holding = False
        self.pressed = set()
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
    def _match(self, code, mask):
        for name, combo in (self.table() or {}).items():
            try:
                c, m = int(combo[0]), int(combo[1])
            except Exception:
                continue
            if c == code and (int(m) & MOD_MASK) == mask:
                return name
        return None

    @objc.python_method
    def _handle(self, ev):
        from AppKit import NSEventTypeKeyDown, NSEventTypeKeyUp

        try:
            if ev.isARepeat() if hasattr(ev, "isARepeat") else False:
                return ev
            action = self._match(int(ev.keyCode()), int(ev.modifierFlags()) & MOD_MASK)
            if action is None:
                return ev
            if ev.type() == NSEventTypeKeyDown:
                if action == "说话":
                    if not self.holding:
                        self.holding = True
                        self.speak_down()
                elif action not in self.pressed:
                    self.pressed.add(action)
                    self.fire(action)
            elif ev.type() == NSEventTypeKeyUp:
                if action == "说话" and self.holding:
                    self.holding = False
                    self.speak_up()
                self.pressed.discard(action)
        except Exception as e:
            log("热键处理出错", e)
        return ev


def ax_trusted():
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


class InputPanel(NSPanel):
    """单行输入面板：无边框但能成为 key window"""

    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True


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
            NSColor.labelColor()
            if not error
            else NSColor.systemRedColor()
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

        host = frost_view(NSMakeRect(0, 0, w, h), 16.0)
        if host is None:
            host = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            host.setWantsLayer_(True)
            rgba = (1.0, 0.93, 0.93, 0.97) if error else (0.99, 0.96, 0.93, 0.97)
            host.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba).CGColor()
            )
            host.layer().setCornerRadius_(16.0)
        host.addSubview_(label)
        win.setContentView_(host)

        fr = self.parent.win.frame()
        o, fw, fh = fr.origin, fr.size.width, fr.size.height
        x = o.x + fw / 2 - w / 2
        y = o.y + fh + 8
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
        self.settings_win = None
        self.danmaku = None
        self.input_panel = None
        self.input_field = None
        self.input_monitor = None
        self.modal = False
        self.reply_event = threading.Event()
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
        try:
            from AppKit import (
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
            )

            self.win.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
            )
        except Exception:
            pass

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
        st = mic_status()
        if st == 2:
            self.bubble.show_text("麦克风权限被拒了：系统设置 → 隐私与安全性 → 麦克风 → 勾「大肥鱼」", 6, error=True)
            return
        if st == 0:
            request_mic()
        try:
            self.rec = Recorder(device=self.audio_device())
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
        wav, peak = self.rec.stop()
        if peak < 60:
            self.set_state("idle")
            self.bubble.show_text("几乎没收到声音——看看麦克风是不是选错了", 5, error=True)
            return
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
                title = str(j.get("标题") or "")
                if ok and title:
                    msg = "已送进「%s」" % title
                if ok and j.get("回落"):
                    msg += "（原绑定会话不在，改用最近活跃）"
                self.performSelectorOnMainThread_withObject_waitUntilDone_(
                    "uiState:", "ok" if (ok and not j.get("回落")) else msg, False
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
        if self.settings.get("弹幕") and self.danmaku is not None:
            self.danmaku.show_text(text)
        if self.settings.get("朗读") and self.tts is not None:
            self.tts.say(text, mode=str(self.settings.get("音色") or "system"))

    @objc.python_method
    def ask_text(self):
        """双击挂件 → 弹系统输入框（NSAlert）。必须先激活 App，否则收不到键盘。"""
        self.close_input()
        try:
            from AppKit import NSAlert

            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            a = NSAlert.alloc().init()
            icon = None
            for cand in (os.path.join(HERE, "assets", "mascot.png"),) + tuple(ASSET_CANDIDATES):
                if os.path.exists(cand):
                    icon = NSImage.alloc().initWithContentsOfFile_(cand)
                    if icon is not None:
                        icon.setSize_(NSMakeSize(48, 48))
                        break
            if icon is not None:
                a.setIcon_(icon)
            a.setMessageText_("打字说")
            a.setInformativeText_("回车发送，Esc 取消")
            a.addButtonWithTitle_("发送")
            a.addButtonWithTitle_("取消")
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 320, 24))
            f.setPlaceholderString_("说点什么…")
            a.setAccessoryView_(f)
            w = a.window()
            w.setLevel_(3)
            w.makeFirstResponder_(f)
            log("输入框弹出")
            self.modal = True
            resp = a.runModal()
            self.modal = False
            if resp == 1000:
                t = str(f.stringValue() or "").strip()
                if t:
                    self.bubble.show_text("你说：%s" % t, 2)
                    self.send(t)
            log("输入框关闭")
        except Exception as e:
            log("打开输入框失败", e)
            self.bubble.show_text("输入框打不开：%s" % e, 5, error=True)

    def sendFromButton_(self, sender):
        self.sendInput_(self.input_field) if self.input_field is not None else None

    def sendInput_(self, sender):
        text = str(sender.stringValue() or "").strip()
        self.close_input()
        if not text:
            return
        self.bubble.show_text("你说：%s" % text, 2)
        self.send(text)

    @objc.python_method
    def close_input(self):
        try:
            if self.input_panel is not None:
                self.input_panel.orderOut_(None)
                self.input_panel = None
                self.input_field = None
        except Exception:
            pass
        try:
            if self.input_monitor is not None:
                from AppKit import NSEvent

                NSEvent.removeMonitor_(self.input_monitor)
                self.input_monitor = None
        except Exception:
            pass

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
        host = frost_view(NSMakeRect(0, 0, w, h), 12.0)
        if host is None:
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
            try:
                self.capture_and_subtitles()
            except Exception as e:
                log("抽台词失败", e)
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
    def capture_and_subtitles(self):
        """截一张 + 认画面底部的字，把台词发给插件（陪看她才知道在演什么）"""
        b64, err = capture_screen()
        if not b64:
            return
        try:
            import base64 as _b64
            import io as _io

            from PIL import Image

            img = Image.open(_io.BytesIO(_b64.b64decode(b64)))
            lines = ocr_screen_text(img, box_hint=0.28)
            if not lines:
                return
            body = json.dumps({"lines": lines}).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8777/hands/subtitle",
                data=body,
                headers={"content-type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8):
                pass
        except Exception as e:
            log("发字幕失败", e)

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

    @objc.python_method
    def audio_device(self):
        idx = self.settings.get("麦克风")
        try:
            if idx is None or idx == "":
                return None
            return int(idx)
        except Exception:
            return None

    @objc.python_method
    def test_mic(self):
        """录 3 秒：先报电平，再报识别结果——排查「no speech detected」用"""
        if self.busy:
            return
        self.busy = True
        self.bubble.show_text("测试中：说句话（3 秒）", 4)

        def run():
            try:
                self.rec.start()
                time.sleep(3.0)
                wav, peak = self.rec.stop()
                if not wav:
                    raise RuntimeError("没录到音频")
                txt, err = self.speech.transcribe(wav)
                try:
                    os.unlink(wav)
                except Exception:
                    pass
                if txt:
                    msg = "峰值 %.0f ✓ 识别到：%s" % (peak, txt)
                else:
                    msg = "峰值 %.0f · 识别失败：%s" % (peak, err or "无文本")
            except Exception as e:
                msg = "测试失败：%s" % e
            self.busy = False
            self.performSelectorOnMainThread_withObject_waitUntilDone_("uiInfo:", msg, False)

        threading.Thread(target=run, daemon=True).start()

    def recSelfTest_(self, sender):
        self.begin_talk()
        time.sleep(3.0)
        self.end_talk()

    def typeMenu_(self, sender):
        self.ask_text()

    def doAsk_(self, sender):
        self.ask_text()

    def testMic_(self, sender):
        self.test_mic()

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
        base = float(self.icon_size())
        alpha = {"idle": 1.0, "listen": 0.9, "think": 0.92}.get(s, 1.0)
        try:
            self.win.setAlphaValue_(alpha if self.settings.get("形象") != "minimal" else alpha * 0.9)
            if s == "listen":
                k = 1.10
                self.iv.setFrameSize_(NSMakeSize(base * k, base * k))
                self.iv.setFrameOrigin_((-base * (k - 1) / 2, -base * (k - 1) / 2))
            else:
                self.iv.setFrame_(NSMakeRect(0, 0, base, base))
        except Exception:
            pass

    @objc.python_method
    def speech_ok(self):
        if self.speech is None:
            self.bubble.show_text("语音模块没准备好", 4, error=True)
            return False
        return True

    @objc.python_method
    def icon_size(self):
        """当前形象该多大（像素）"""
        base = int(self.settings.get("尺寸") or BALL)
        if self.settings.get("形象") == "minimal":
            return max(20, int(base * 0.30))
        return max(48, min(320, base))

    @objc.python_method
    def apply_display_mode(self, mode=None):
        mode = mode or self.settings.get("形象", "image")
        self.settings["形象"] = mode
        size = self.icon_size()
        try:
            if mode == "minimal":
                path = os.path.join(HERE, "assets", "dot.png")
                img = NSImage.alloc().initWithContentsOfFile_(path) if os.path.exists(path) else None
                img = img or placeholder_image(size)
                self.win.setAlphaValue_(0.92)
            else:
                cands = list(ASSET_CANDIDATES)
                if mode == "mascot":
                    cands = [os.path.join(HERE, "assets", "mascot.png")] + cands
                img = None
                for cand in cands:
                    if os.path.exists(cand):
                        img = NSImage.alloc().initWithContentsOfFile_(cand)
                        if img is not None:
                            break
                img = img or placeholder_image(size)
                self.win.setAlphaValue_(1.0)
            self.iv.setImage_(img)
            f = self.win.frame()
            self.win.setFrame_display_(NSMakeRect(f.origin.x, f.origin.y, size, size), False)
            self.iv.setFrame_(NSMakeRect(0, 0, size, size))
        except Exception as e:
            log("换形象失败", e)

    @objc.python_method
    def set_icon_size(self, px):
        self.settings["尺寸"] = max(48, min(320, int(px)))
        save_settings(self.settings)
        self.apply_display_mode()

    @objc.python_method
    def apply_widget_enabled(self, on):
        self.settings["挂件"] = bool(on)
        try:
            if on:
                self.win.orderFrontRegardless()
                self.iv.setHidden_(False)
            else:
                self.win.orderOut_(None)
            if not on:
                self.bubble.show_text("挂件已隐藏 · 菜单栏 🐋 还能打开设置", 3)
        except Exception:
            pass

    @objc.python_method
    def rebuild_hotkeys(self):
        if self.hotkey is None:
            return
        self.hotkey.stop()
        if self.settings.get("热键"):
            self.hotkey.start()

    @objc.python_method
    def fire_action(self, name):
        if name == "陪看":
            self.toggle_watch()
        elif name == "看一眼":
            self.look_now()
        elif name == "设置":
            self.openSettings_(None)

    def hideWidget_(self, sender):
        self.settings["挂件"] = False
        save_settings(self.settings)
        self.apply_widget_enabled(False)

    def reshowNow_(self, tag):
        try:
            if getattr(self, "modal", False):
                return
            if self.settings.get("挂件", True):
                self.win.orderFrontRegardless()
                self.win.setAlphaValue_(1.0)
            log("重新显示(%s)：visible=%s" % (tag, self.win.isVisible()))
        except Exception as e:
            log("重新显示失败", e)

    def showWidget_(self, sender):
        self.settings["挂件"] = True
        save_settings(self.settings)
        self.apply_widget_enabled(True)
        self.win.orderFrontRegardless()

    def openSettings_(self, sender):
        if self.settings_win is None:
            self.settings_win = SettingsWindow.alloc().initWithWhale_(self)
        self.settings_win.refresh()
        self.settings_win.show()

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
        itt = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("测试麦克风 / 语音识别", "testMic:", "")
        itt.setTarget_(self)
        m.addItem_(itt)
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
        itc = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("设置…", "openSettings:", ",")
        itc.setTarget_(self)
        m.addItem_(itc)
        m.addItem_(NSMenuItem.separatorItem())
        it_t = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打字说…", "typeMenu:", "t")
        it_t.setTarget_(self)
        m.addItem_(it_t)
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


# ---------------------------------------------------------------- 设置窗口
class SettingsWindow(NSObject):
    """挂件开关 / 形象 / 全局热键 / 朗读 / 陪看间隔"""

    def initWithWhale_(self, whale):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self.whale = whale
        self.win = None
        self.recorder = None
        self.build()
        return self

    @objc.python_method
    def build(self):
        w, h = 520.0, 828.0
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, w, h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        self.win.setTitle_("大肥鱼 设置")
        self.win.setReleasedWhenClosed_(False)
        self.win.center()
        v = self.win.contentView()

        def label(text, x, y, ww, size=13, bold=False, gray=False):
            f = NSTextField.labelWithString_(text)
            f.setFrame_(NSMakeRect(x, y, ww, 20))
            f.setFont_(
                NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
            )
            if gray:
                f.setTextColor_(NSColor.secondaryLabelColor())
            v.addSubview_(f)
            return f

        y = h - 40
        label("大肥鱼 · 设置", 20, y, 300, size=16, bold=True)

        # 1) 挂件开关
        y -= 40
        self.cb_widget = NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 300, 24))
        self.cb_widget.setButtonType_(3)
        self.cb_widget.setTitle_("显示挂件（关掉只留菜单栏）")
        self.cb_widget.setTarget_(self)
        self.cb_widget.setAction_("toggleWidget:")
        v.addSubview_(self.cb_widget)

        # 2) 形象（三选一）
        y -= 38
        label("形象", 20, y + 3, 60)
        self.seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(80, y - 1, 330, 26))
        self.seg.setSegmentCount_(3)
        self.seg.setLabel_forSegment_("官方鲸鱼", 0)
        self.seg.setLabel_forSegment_("极简圆点", 1)
        self.seg.setLabel_forSegment_("看板娘", 2)
        self.seg.setTarget_(self)
        self.seg.setAction_("modeChanged:")
        v.addSubview_(self.seg)

        # 3) 尺寸滑条
        y -= 34
        label("大小", 20, y + 3, 60)
        self.slider = NSSlider.alloc().initWithFrame_(NSMakeRect(80, y - 2, 300, 26))
        self.slider.setMinValue_(48)
        self.slider.setMaxValue_(320)
        self.slider.setContinuous_(True)
        self.slider.setTarget_(self)
        self.slider.setAction_("sizeChanged:")
        v.addSubview_(self.slider)
        self.lbl_size = label("132 px", 390, y + 3, 80, size=11, gray=True)

        # 4) 热键
        y -= 44
        label("全局热键", 20, y, 90, bold=True)
        self.hotkey_buttons = {}
        for i, (name, desc) in enumerate(HOTKEY_ACTIONS):
            y -= 34
            label(name, 34, y + 3, 60)
            btn = NSButton.alloc().initWithFrame_(NSMakeRect(96, y - 2, 150, 26))
            btn.setBezelStyle_(1)
            btn.setTag_(i)
            btn.setTarget_(self)
            btn.setAction_("recordHotkey:")
            v.addSubview_(btn)
            self.hotkey_buttons[name] = btn
            label(desc, 256, y + 3, 190, size=11, gray=True)
        y -= 26
        self.lbl_hint = label("", 96, y, 360, size=11, gray=True)

        # 5) 朗读
        y -= 36
        self.cb_speak = NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 340, 24))
        self.cb_speak.setButtonType_(3)
        self.cb_speak.setTitle_("念出来（用系统语音读她的回话）")
        self.cb_speak.setTarget_(self)
        self.cb_speak.setAction_("toggleSpeak:")
        v.addSubview_(self.cb_speak)

        # 6) 陪看间隔
        y -= 40
        label("陪看间隔", 20, y + 3, 70)
        self.step = NSStepper.alloc().initWithFrame_(NSMakeRect(96, y - 1, 19, 27))
        self.step.setMinValue_(10)
        self.step.setMaxValue_(120)
        self.step.setIncrement_(10)
        self.step.setValueWraps_(False)
        self.step.setTarget_(self)
        self.step.setAction_("intervalChanged:")
        v.addSubview_(self.step)
        self.lbl_interval = label("20 秒", 124, y + 3, 80)

        # 7) 弹幕
        y -= 40
        self.cb_danmaku = NSButton.alloc().initWithFrame_(NSMakeRect(20, y, 380, 24))
        self.cb_danmaku.setButtonType_(3)
        self.cb_danmaku.setTitle_("弹幕（回话从屏幕上滑过去）")
        self.cb_danmaku.setTarget_(self)
        self.cb_danmaku.setAction_("toggleDanmaku:")
        v.addSubview_(self.cb_danmaku)

        # 9) 音色
        y -= 38
        label("音色", 20, y + 3, 60)
        self.seg_voice = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(80, y - 1, 300, 26))
        self.seg_voice.setSegmentCount_(2)
        self.seg_voice.setLabel_forSegment_("系统音色", 0)
        self.seg_voice.setLabel_forSegment_("晓晓 · 在线", 1)
        self.seg_voice.setTarget_(self)
        self.seg_voice.setAction_("voiceChanged:")
        v.addSubview_(self.seg_voice)
        label("在线音色更像真人，但要联网", 80, y - 24, 360, size=11, gray=True)

        # 10) 弹幕字号
        y -= 38
        label("弹幕字号", 20, y + 3, 80)
        self.slider_dm = NSSlider.alloc().initWithFrame_(NSMakeRect(104, y - 2, 280, 26))
        self.slider_dm.setMinValue_(16)
        self.slider_dm.setMaxValue_(56)
        self.slider_dm.setContinuous_(True)
        self.slider_dm.setTarget_(self)
        self.slider_dm.setAction_("danmakuSizeChanged:")
        v.addSubview_(self.slider_dm)
        self.lbl_dm = label("30 px", 392, y + 3, 80, size=11, gray=True)

        # 11) 弹幕字体（列出系统里所有字体族）
        y -= 36
        label("弹幕字体", 20, y + 3, 80)
        self.pop_font = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(104, y - 3, 320, 28), False
        )
        self.pop_font.setTarget_(self)
        self.pop_font.setAction_("fontPicked:")
        v.addSubview_(self.pop_font)

        # 12.5) 麦克风
        y -= 38
        label("麦克风", 20, y + 3, 80)
        self.pop_mic = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(104, y - 3, 320, 28), False
        )
        self.pop_mic.setTarget_(self)
        self.pop_mic.setAction_("micPicked:")
        v.addSubview_(self.pop_mic)

        # 13) 识别提示
        y -= 40
        label("识别提示", 20, y + 3, 80)
        self.fld_hint = NSTextField.alloc().initWithFrame_(NSMakeRect(104, y - 1, 300, 26))
        self.fld_hint.setPlaceholderString_("人名、专有名词，逗号分隔")
        self.fld_hint.setTarget_(self)
        self.fld_hint.setAction_("hintChanged:")
        v.addSubview_(self.fld_hint)
        label("给识别器一点上下文，专有名词更准", 104, y - 26, 340, size=11, gray=True)

        # 关闭
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(w - 120, 18, 100, 30))
        btn.setBezelStyle_(1)
        btn.setTitle_("关闭")
        btn.setTarget_(self)
        btn.setAction_("closeWin:")
        v.addSubview_(btn)

    @objc.python_method
    def refresh(self):
        st = self.whale.settings
        self.cb_widget.setState_(1 if st.get("挂件", True) else 0)
        mode = st.get("形象") or "image"
        self.seg.setSelectedSegment_({"image": 0, "minimal": 1, "mascot": 2}.get(mode, 0))
        size = int(st.get("尺寸") or 132)
        self.slider.setIntegerValue_(size)
        self.lbl_size.setStringValue_("%d px" % size)
        self.cb_speak.setState_(1 if st.get("朗读") else 0)
        self.cb_danmaku.setState_(1 if st.get("弹幕") else 0)
        self.seg_voice.setSelectedSegment_(1 if st.get("音色") == "edge" else 0)
        self.slider_dm.setIntegerValue_(int(st.get("弹幕字号") or 30))
        self.lbl_dm.setStringValue_("%d px" % int(st.get("弹幕字号") or 30))
        fams = ["系统粗体"] + system_font_families()
        cur_font = str(st.get("弹幕字体") or "")
        if cur_font in ("bold", "rounded", "pingfang"):
            cur_font = ""
        title = cur_font or "系统粗体"
        if title not in fams:
            fams.insert(1, title)
        if self.pop_font.numberOfItems() != len(fams):
            self.pop_font.removeAllItems()
            self.pop_font.addItemsWithTitles_(fams)
        self.pop_font.selectItemWithTitle_(title)

        devs = input_devices()
        self.mic_items = [(None, "系统默认")] + devs
        titles = [n for _, n in self.mic_items]
        if self.pop_mic.numberOfItems() != len(titles):
            self.pop_mic.removeAllItems()
            self.pop_mic.addItemsWithTitles_(titles)
        cur = st.get("麦克风")
        idx = 0
        for i, (d, _n) in enumerate(self.mic_items):
            if d is not None and cur is not None and int(d) == int(cur):
                idx = i
        self.pop_mic.selectItemAtIndex_(idx)
        self.fld_hint.setStringValue_(str(st.get("识别提示") or ""))
        self.step.setIntegerValue_(int(st.get("陪看间隔") or 20))
        self.lbl_interval.setStringValue_("%d 秒" % int(st.get("陪看间隔") or 20))
        table = st.get("热键表") or {}
        for name, btn in self.hotkey_buttons.items():
            combo = table.get(name) or [49, 1 << 19]
            btn.setTitle_(key_name(int(combo[0]), int(combo[1])))
        self.lbl_hint.setStringValue_(
            "快捷键默认 ⌥Space / ⌥P / ⌥L / ⌥S；点按钮即可改" if st.get("热键")
            else "全局热键总开关是关的（只有菜单和鲸鱼可用）"
        )
        self.lbl_hint.setTextColor_(NSColor.secondaryLabelColor())

    @objc.python_method
    def show(self):
        self.refresh()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.win.makeKeyAndOrderFront_(None)

    def closeWin_(self, sender):
        self.win.orderOut_(None)

    def toggleWidget_(self, sender):
        on = bool(sender.state())
        self.whale.settings["挂件"] = on
        save_settings(self.whale.settings)
        self.whale.apply_widget_enabled(on)

    def toggleSpeak_(self, sender):
        on = bool(sender.state())
        self.whale.settings["朗读"] = on
        save_settings(self.whale.settings)
        if not on and self.whale.tts is not None:
            self.whale.tts.stop()

    def toggleDanmaku_(self, sender):
        self.whale.settings["弹幕"] = bool(sender.state())
        save_settings(self.whale.settings)

    def danmakuSizeChanged_(self, sender):
        px = int(sender.integerValue())
        self.lbl_dm.setStringValue_("%d px" % px)
        self.whale.settings["弹幕字号"] = px
        save_settings(self.whale.settings)

    def fontPicked_(self, sender):
        fam = str(sender.titleOfSelectedItem() or "").strip()
        if fam == "系统粗体":
            fam = ""
        self.whale.settings["弹幕字体"] = fam
        save_settings(self.whale.settings)

    def micPicked_(self, sender):
        i = int(sender.indexOfSelectedItem())
        items = getattr(self, "mic_items", [(None, "系统默认")])
        if 0 <= i < len(items):
            dev = items[i][0]
            self.whale.settings["麦克风"] = dev
            save_settings(self.whale.settings)
            self.whale.performSelectorOnMainThread_withObject_waitUntilDone_(
                "uiInfo:", "麦克风：%s" % items[i][1], False
            )

    def danmakuFontChanged_(self, sender):
        self.whale.settings["弹幕字体"] = {0: "bold", 1: "rounded", 2: "pingfang"}.get(
            int(sender.selectedSegment()), "bold"
        )
        save_settings(self.whale.settings)

    def hintChanged_(self, sender):
        words = str(sender.stringValue() or "").strip()
        self.whale.settings["识别提示"] = words
        if self.whale.speech is not None:
            self.whale.speech.hint_words = words
        save_settings(self.whale.settings)

    def voiceChanged_(self, sender):
        self.whale.settings["音色"] = "edge" if int(sender.selectedSegment()) == 1 else "system"
        save_settings(self.whale.settings)

    def modeChanged_(self, sender):
        mode = {0: "image", 1: "minimal", 2: "mascot"}.get(int(sender.selectedSegment()), "image")
        self.whale.settings["形象"] = mode
        save_settings(self.whale.settings)
        self.whale.apply_display_mode(mode)

    def sizeChanged_(self, sender):
        px = int(sender.integerValue())
        self.lbl_size.setStringValue_("%d px" % px)
        self.whale.settings["尺寸"] = px
        self.whale.apply_display_mode()
        save_settings(self.whale.settings)

    def intervalChanged_(self, sender):
        n = int(sender.integerValue())
        self.whale.settings["陪看间隔"] = n
        self.whale.watch_interval = float(n)
        self.lbl_interval.setStringValue_("%d 秒" % n)
        save_settings(self.whale.settings)

    def recordHotkey_(self, sender):
        from AppKit import NSEvent, NSEventMaskKeyDown

        name = HOTKEY_ACTIONS[int(sender.tag())][0]
        if self.recorder is not None:
            NSEvent.removeMonitor_(self.recorder)
            self.recorder = None
        self.lbl_hint.setStringValue_("给「%s」按下组合键…（Esc 取消）" % name)
        self.lbl_hint.setTextColor_(NSColor.secondaryLabelColor())
        sender.setTitle_("…")

        def handler(ev):
            code = int(ev.keyCode())
            mask = int(ev.modifierFlags()) & MOD_MASK
            if code == 53:  # Esc
                self.stop_record()
                self.refresh()
                return ev
            table = self.whale.settings.setdefault("热键表", {})
            bad = hotkey_conflict(code, mask, table, skip=name)
            if bad:
                self.lbl_hint.setStringValue_(bad)
                self.lbl_hint.setTextColor_(NSColor.systemRedColor())
                self.stop_record()
                self.refresh()
                return ev
            table[name] = [code, mask]
            save_settings(self.whale.settings)
            self.stop_record()
            self.whale.rebuild_hotkeys()
            self.refresh()
            self.lbl_hint.setStringValue_("「%s」改好了：%s" % (name, key_name(code, mask)))
            return ev

        self.recorder = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, handler
        )

    @objc.python_method
    def stop_record(self):
        from AppKit import NSEvent

        if self.recorder is not None:
            try:
                NSEvent.removeMonitor_(self.recorder)
            except Exception:
                pass
            self.recorder = None


# ---------------------------------------------------------------- 回话服务
class ReplyServer(ThreadingHTTPServer):
    daemon_threads = True


def mic_probe(seconds=2.0):
    """两种录法各测一次，排查「有权限但全是 0」"""
    import numpy as np
    import sounddevice as sd

    out = {"device": input_device_name(), "status": mic_status()}
    # A. sd.rec 阻塞式
    try:
        a = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        out["rec_peak"] = int(np.abs(a).max()) if a.size else -1
    except Exception as e:
        out["rec_err"] = str(e)
    # B. InputStream 回调（挂件实际用的）
    try:
        buf = []
        st = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024,
            callback=lambda indata, frames, t, status: buf.append(bytes(indata)),
        )
        st.start()
        import time as _t
        _t.sleep(seconds)
        st.stop()
        st.close()
        raw = b"".join(buf)
        arr = np.frombuffer(raw, dtype=np.int16) if raw else np.zeros(0, dtype=np.int16)
        out["stream_peak"] = int(np.abs(arr).max()) if arr.size else -1
        out["stream_bytes"] = len(raw)
    except Exception as e:
        out["stream_err"] = str(e)
    return out


def start_reply_server(on_text, on_open_settings=None, on_show=None, on_hide=None, state=None, on_type=None):
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
            path = str(self.path or "/").split("?")[0]
            if path == "/settings" and on_open_settings:
                on_open_settings()
                return self._send({"ok": True, "说": "设置打开了"})
            if path == "/hide" and on_hide:
                on_hide()
                return self._send({"ok": True, "说": "挂件藏起来了"})
            if path == "/show" and on_show:
                on_show()
                return self._send({"ok": True, "说": "挂件出来了"})
            if path == "/type":
                if on_type:
                    on_type()
                return self._send({"ok": True, "说": "打开输入框"})
            if path == "/rec-test":
                r = Recorder()
                r.start()
                time.sleep(2.0)
                wav, peak = r.stop()
                return self._send({"ok": True, "peak": peak, "wav": wav})
            if path == "/mic-test":
                return self._send({"ok": True, **mic_probe()})
            if path == "/state":
                return self._send({"ok": True, **(state() if state else {})})
            self._send({"ok": True, "说": "鱼搭子在"})

        def do_POST(self):
            path = str(self.path or "/").split("?")[0]
            if path == "/settings" and on_open_settings:
                on_open_settings()
                return self._send({"ok": True, "说": "设置打开了"})
            if path == "/show" and on_show:
                on_show()
                return self._send({"ok": True, "说": "挂件出来了"})
            if path == "/hide" and on_hide:
                on_hide()
                return self._send({"ok": True, "说": "挂件藏起来了"})
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
    try:
        import faulthandler

        faulthandler.enable(file=open(os.path.join(HERE, "crash.log"), "a"))
    except Exception:
        pass
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    whale = Whale.alloc().init()
    whale.build()
    whale.bubble = Bubble.alloc().initWithParent_(whale)
    whale.danmaku = Danmaku.alloc().initWithParent_(whale)

    speech = Speech(hint_words=str(whale.settings.get("识别提示") or ""))
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

    start_reply_server(
        lambda t: whale.performSelectorOnMainThread_withObject_waitUntilDone_("speak:", t, False),
        on_open_settings=lambda: whale.performSelectorOnMainThread_withObject_waitUntilDone_(
            "openSettings:", None, False
        ),
        on_show=lambda: whale.performSelectorOnMainThread_withObject_waitUntilDone_(
            "showWidget:", None, False
        ),
        on_hide=lambda: whale.performSelectorOnMainThread_withObject_waitUntilDone_(
            "hideWidget:", None, False
        ),
        on_type=lambda: whale.performSelectorOnMainThread_withObject_waitUntilDone_(
            "doAsk:", None, False
        ),
        state=lambda: {
            "version": VERSION,
            "watching": bool(whale.watching),
            "形象": whale.settings.get("形象"),
            "挂件": whale.settings.get("挂件"),
            "麦克风": mic_status(),
            "输入设备": input_device_name(),
        },
    )

    whale.tts = TTS()
    whale.hotkey = Hotkeys(
        whale.begin_talk,
        whale.end_talk,
        whale.fire_action,
        lambda: whale.settings.get("热键表") or {},
    )
    if whale.settings.get("热键"):
        if not whale.hotkey.start():
            log("全局热键没起来（缺辅助功能权限），只能按住鲸鱼说话")
        elif not ax_trusted():
            log("热键在跑，但系统可能还没给「辅助功能」权限")

    # 状态栏图标，方便退出
    item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
    item.button().setTitle_("🐋")
    menu = NSMenu.alloc().init()
    m_type = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("打字说…", "typeMenu:", "t")
    m_type.setTarget_(whale)
    menu.addItem_(m_type)
    m_set = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("设置…", "openSettings:", ",")
    m_set.setTarget_(whale)
    menu.addItem_(m_set)
    menu.addItem_(NSMenuItem.separatorItem())
    mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "quit:", "q")
    mi.setTarget_(whale)
    menu.addItem_(mi)
    item.setMenu_(menu)
    whale.status_item = item

    if os.environ.get("FISH_TEST_SHOT"):
        def run_shot():
            time.sleep(1.5)
            b64, err = capture_screen()
            if b64:
                with open(os.path.join(HERE, "shot.png"), "wb") as f:
                    f.write(base64.b64decode(b64))
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
                wav, peak = r.stop()
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

    whale.apply_display_mode(os.environ.get("FISH_TEST_MODE") or whale.settings.get("形象", "image"))
    if whale.settings.get("挂件", True):
        whale.apply_widget_enabled(True)      # 显式露头一次，避免"配置勾了却没显示"
    else:
        whale.apply_widget_enabled(False)

    if os.environ.get("FISH_TEST_REC"):
        def rec_hook(t0=time.time()):
            time.sleep(2.0)
            whale.performSelectorOnMainThread_withObject_waitUntilDone_("recSelfTest:", None, False)
        threading.Thread(target=rec_hook, daemon=True).start()

    if os.environ.get("FISH_TEST_INPUT"):
        def run_input():
            time.sleep(2.0)
            whale.performSelectorOnMainThread_withObject_waitUntilDone_("doAsk:", None, False)
        threading.Thread(target=run_input, daemon=True).start()

    if os.environ.get("FISH_TEST_SETTINGS"):
        def run_settings():
            time.sleep(1.5)
            whale.performSelectorOnMainThread_withObject_waitUntilDone_(
                "openSettings:", None, False
            )
        threading.Thread(target=run_settings, daemon=True).start()

    for delay, tag in ((1.5, "1.5s"), (5.0, "5s")):
        def later(t=tag):
            time.sleep(delay)
            whale.performSelectorOnMainThread_withObject_waitUntilDone_("reshowNow:", t, False)
        threading.Thread(target=later, daemon=True).start()

    log("起来了：8778 收话，8777 送话")
    bubble_tip = "按住我说话 · 双击我打字 · 右键更多"
    whale.bubble.show_text(bubble_tip, 8)
    app.run()


if __name__ == "__main__":
    main()
