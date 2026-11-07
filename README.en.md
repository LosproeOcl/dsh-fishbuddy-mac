# DSH FishBuddy for macOS

> A native desktop companion for DeepSeek Harness: hold to talk, watch together, hear the reply.
> All traffic stays on `127.0.0.1` (the optional online voice excepted).

[![CI](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml/badge.svg)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LosproeOcl/dsh-fishbuddy-mac?display_name=tag)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/releases)
[![License: MIT](https://img.shields.io/badge/code%20license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)](#requirements)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.12-blue)](requirements.txt)

[简体中文](README.md) · **English**

<p align="center">
  <img src="assets/mascot.png" width="140" alt="mascot">
  <img src="assets/whale.png" width="140" alt="official whale">
</p>

---

## Overview

DSH FishBuddy is a native macOS widget that acts as the voice front-end of DeepSeek Harness:

- **You speak, it listens** — hold the icon (or a global hotkey); on-device speech recognition
  turns your voice into text and injects it into the bound session.
- **It speaks back** — the last message of a turn is pushed back as a frosted bubble, optionally
  as a scrolling danmaku line, and optionally read aloud.
- **It watches with you** — in watch mode it periodically screenshots the screen, OCRs the
  subtitle band with Vision, and sends both the frame and the captured lines as context.
- **It knows your screen** — subtitles are only sent when text is actually detected.

The only outbound traffic is the optional `edge-tts` neural voice; switch back to the system
voice to keep everything local.

## Features

| Area | Capability | Permission |
|---|---|---|
| Voice input | Hold-to-talk, four configurable global hotkeys | Microphone, Speech Recognition |
| Voice output | Best installed system voice, or Edge neural voice (`zh-CN-XiaoxiaoNeural`) | Network (online voice only) |
| Personas | Official whale / minimal dot / mascot, 48–320 px size slider | — |
| Reply surface | Frosted-glass bubble, danmaku line (font family + 16–56 px), optional TTS | — |
| Watch mode | Periodic screenshots, Vision OCR of subtitle band, context injection | Screen Recording |
| Automation | Hotkeys with conflict detection (system shortcuts + duplicates) | Accessibility (optional) |
| Settings | Native window persisted to `~/.dsh/fishbuddy-mac.json` | — |

### Personas

| Official whale | Minimal dot | Mascot |
|---|---|---|
| ![](assets/whale.png) | ![](assets/dot.png) | ![](assets/mascot.png) |
| DeepSeek brand mark (trademark of DeepSeek) | Flat dot, no glow | Whale-girl fan art (CC BY-NC-SA 4.0) |

> The mascot and the official mark are **not** MIT and **not** for commercial use.
> See [THIRD-PARTY.md](THIRD-PARTY.md).

## Requirements

- macOS 13 Ventura or later (tested on macOS 26, Apple Silicon)
- Python 3.9+ (CI covers 3.9 and 3.12; developed against 3.14)
- DeepSeek Harness with plugin support
- ~200 MB disk for the virtual environment

## Installation

```sh
git clone https://github.com/LosproeOcl/dsh-fishbuddy-mac.git
cd dsh-fishbuddy-mac

./install.sh                 # venv + deps + DSH-FishBuddy.app
dsh plugin --profile desktop add ./plugin
open DSH-FishBuddy.app
```

Manual equivalent:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./build.sh .venv/bin/python
```

> Always launch through `open DSH-FishBuddy.app`. macOS TCC (microphone, speech recognition,
> screen recording) binds permissions to the app bundle identity; running `python main.py`
> directly cannot obtain them.

## Permissions

| Permission | Used by | Without it |
|---|---|---|
| Microphone | Hold-to-talk | Bubble reports that the mic cannot be opened |
| Speech Recognition | All transcription | Bubble asks you to enable it in System Settings |
| Screen Recording | Watch mode, “take a look” | Bubble offers a shortcut to the settings pane |
| Accessibility | Global hotkeys | Hotkeys silently do nothing; the icon still works |

Quit and relaunch the widget after changing permissions.

## Configuration

### Plugin (`~/.dsh/fishbuddy-mac-plugin.json`)

```json
{
  "会话": "session-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "回调": "http://127.0.0.1:8778/hands/reply",
  "挂件路径": "/Applications/DSH-FishBuddy.app",
  "端口": 8777
}
```

The same values are editable in **DSH → Settings → 大肥鱼**, which also offers
*Launch widget*, *Open widget settings*, *Show*, *Hide* and a self-check.

### Widget (`~/.dsh/fishbuddy-mac.json`)

| Key | Default | Meaning |
|---|---|---|
| `挂件` | `true` | Show the icon (the menu bar item always exists) |
| `形象` | `image` | `image` / `minimal` / `mascot` |
| `尺寸` | `132` | Icon edge length in px (48–320) |
| `朗读` | `true` | Speak replies aloud |
| `音色` | `system` | `system` or `edge` (online neural voice) |
| `麦克风` | `null` | Input device index; `null` = system default |
| `弹幕` | `true` | Render replies as danmaku |
| `弹幕字号` | `30` | Danmaku font size (16–56 px) |
| `弹幕字体` | `""` | Font family; empty = system bold |
| `识别提示` | `""` | Comma-separated contextual words for the recognizer |
| `陪看间隔` | `20` | Watch-mode screenshot interval (seconds) |
| `热键表` | see below | Per-action key bindings |

Default hotkeys: `⌥Space` talk, `⌥P` watch toggle, `⌥L` look now, `⌥S` settings.
Bindings are validated: a modifier is required, system shortcuts and duplicate bindings are rejected.

## Architecture

```
┌────────────────────────────┐        loopback HTTP         ┌──────────────────────────┐
│  DSH-FishBuddy.app         │                              │  DSH plugin              │
│  (PyObjC, accessory app)   │  POST 8777/hands/say         │  dsh-fishbuddy-mac       │
│                            │  POST 8777/hands/frame  ───► │                          │
│  • NSWindow overlays       │  POST 8777/hands/subtitle    │  • session delivery      │
│  • SFSpeechRecognizer      │  GET  8777/hands/ping        │  • reply capture         │
│  • AVSpeechSynthesizer     │                              │  • settings page         │
│  • Vision OCR              │  POST 8778/hands/reply  ◄─── │  • widget controls       │
│  • sounddevice + numpy     │  POST 8778/settings|show|hide│                          │
└────────────────────────────┘                              └──────────────────────────┘
                                                                     │
                                                                     ▼
                                                             DSH session controller
```

- The **widget** owns audio capture, recognition, rendering and OS integration.
- The **plugin** owns session binding, message delivery, reply capture (reasoning segments are
  filtered out) and the settings UI.

## Protocol

| Direction | Endpoint | Payload |
|---|---|---|
| widget → plugin | `POST /hands/say` | `{"text": "…"}` |
| widget → plugin | `POST /hands/frame` | `{"图片": "<base64>", "存档": 0\|1, "立即": 0\|1, "来源": "陪看"}` |
| widget → plugin | `POST /hands/subtitle` | `{"lines": ["…"]}` |
| widget → plugin | `GET /hands/ping` | — |
| plugin → widget | `POST /hands/reply` | `{"text": "…", "session": "session-…"}` |
| plugin → widget | `POST /settings` · `/show` · `/hide` | — |
| plugin → widget | `GET /state` | version, persona, mic status, watch state |

The plugin prefixes the most recent 30 s of captured subtitles to outgoing utterances, so the
agent knows what is on screen without spending an extra turn.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/ruff check .          # lint
.venv/bin/python -m pytest -q   # smoke tests
./build.sh .venv/bin/python     # build the .app
python tools/make_assets.py     # regenerate assets (needs cairosvg)
```

Layout:

```
main.py                 widget: windows, audio, ASR, OCR, TTS, danmaku, settings, local server
plugin/                 DSH plugin: session bridge, settings UI, diagnostics
tools/make_assets.py    asset generation (whale from Twemoji SVG, dot drawn in code)
tests/                  smoke tests
.github/workflows/      CI (ruff + pytest + build) and Release (zip + checksum)
```

Debug switches (environment variables; use `launchctl setenv` before `open`):

| Variable | Effect |
|---|---|
| `FISH_TEST_SHOT=1` | Capture a screenshot at startup to verify Screen Recording |
| `FISH_TEST_MIC=1` | Record 1.5 s at startup and report the frame count |
| `FISH_TEST_WAV=/p.wav` | Transcribe a file at startup and log the result |
| `FISH_TEST_SETTINGS=1` | Open the settings window at startup |
| `FISH_TEST_MODE=minimal` | Force a persona without persisting it |
| `FISH_TEST_REC=1` | Run one main-thread recording cycle |

## Release

1. Update `VERSION` in `main.py` and add a `CHANGELOG.md` entry.
2. `git tag v0.x.y && git push origin v0.x.y`
3. The release workflow validates tag ↔ version, runs tests, builds a zip with a SHA-256
   checksum, and publishes a GitHub Release.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No speech detected` | Input level too low (Bluetooth headset) | Choose another microphone in settings, or speak closer |
| Proper nouns misrecognized | Unknown to the model | Add them under *识别提示* |
| Screenshots are black | Screen Recording denied | Re-grant, relaunch |
| Hotkeys do nothing | Accessibility denied | Enable it for “大肥鱼”, relaunch |
| Widget invisible | Hidden via the plugin, or on another Space | Menu bar icon → Settings → show; the window joins all Spaces |

## Privacy and security

- Audio, screenshots and subtitles stay in memory and under `~/.dsh`; frames are written to
  `~/.dsh/fishbuddy-frames`.
- Plugin routes pass DSH's trust fence (`connection.requestRejection`) with a loopback-only fallback.
- The only outbound path is the optional Edge voice, which sends the reply text to Microsoft.

## License

Code (widget and plugin) is [MIT](LICENSE).

Artwork is **not** MIT: the official whale belongs to DeepSeek (unofficial project), and the
mascot is CC BY-NC-SA 4.0 (non-commercial). See [THIRD-PARTY.md](THIRD-PARTY.md).
Replace `assets/whale.png` and `assets/mascot.png` to redistribute under your own terms.
