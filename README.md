# DSH 大肥鱼 · macOS 挂件

> 桌面上的 AI 伴侣：按住说话、陪你看屏幕、把回话念出来。
> 通过本机回环协议与 [DeepSeek Harness](https://www.deepseek.com/) 通信，数据不出本机（在线音色除外）。

[![CI](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml/badge.svg)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LosproeOcl/dsh-fishbuddy-mac?display_name=tag)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/releases)
[![License: MIT](https://img.shields.io/badge/code%20license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)](#系统要求)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.12-blue)](requirements.txt)

**简体中文** · [English](README.en.md)

<p align="center">
  <img src="assets/mascot.png" width="140" alt="看板娘">
  <img src="assets/whale.png" width="140" alt="官方鲸鱼">
</p>

---

## 简介

DSH 大肥鱼是一个原生 macOS 桌面挂件，作为 DeepSeek Harness 的语音前端：

- **你说，它听** —— 按住图标（或全局热键）说话，本机语音识别转成文字，投递到你绑定的会话
- **它说，你听** —— 一轮结束时把最后一段回话推回来：磨砂气泡、可选弹幕、可选朗读
- **它陪你看** —— 陪看模式下定时截屏，用 Vision OCR 抽画面字幕区的台词，和截图一起作为上下文
- **它认得你的屏幕** —— 截屏只在看到字幕时送字幕；送图统一走 `/hands/frame`

全部通信走 `127.0.0.1:8777 / 8778`。唯一可能的外网流量是 `edge-tts` 在线音色，可在设置里切回系统音色。

## 功能

| 模块 | 能力 | 所需权限 |
|---|---|---|
| 语音输入 | 按住说话、全局热键、按住即录 | 麦克风、语音识别 |
| 语音输出 | 系统音色（自动挑最高质量）或 Edge 在线神经音色 | 网络（仅在线音色） |
| 形象 | 官方鲸鱼 / 极简圆点 / 看板娘，48–320 px 滑条 | — |
| 回话呈现 | 磨砂气泡、弹幕（字体族 + 16–56 px 字号）、朗读 | — |
| 陪看 | 定时截屏、Vision OCR 抽台词、上下文注入 | 屏幕录制 |
| 自动化 | 四个可配置全局热键，冲突检测（系统快捷键 + 动作互撞） | 辅助功能（可选） |
| 设置 | 原生设置窗口，持久化到 `~/.dsh/fishbuddy-mac.json` | — |

### 三种形象

| 官方鲸鱼 | 极简圆点 | 看板娘 |
|---|---|---|
| ![](assets/whale.png) | ![](assets/dot.png) | ![](assets/mascot.png) |
| DeepSeek 品牌标志（商标归 DeepSeek） | 平涂圆点，无光晕 | 鲸鱼娘同人图（CC BY-NC-SA 4.0） |

> 看板娘与官方鲸鱼**不属于 MIT**，也不可商用；详见 [THIRD-PARTY.md](THIRD-PARTY.md)。

## 系统要求

- macOS 13 Ventura 及以上（在 macOS 26 / Apple Silicon 实测）
- Python 3.9+（CI 覆盖 3.9 与 3.12；开发环境为 3.14）
- 已安装 DeepSeek Harness，且支持插件
- 约 200 MB 磁盘（虚拟环境）

## 安装

```sh
git clone https://github.com/LosproeOcl/dsh-fishbuddy-mac.git
cd dsh-fishbuddy-mac

./install.sh                 # 建 .venv、装依赖、生成 DSH-FishBuddy.app
dsh plugin --profile desktop add ./plugin
open DSH-FishBuddy.app
```

手动等价步骤：

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./build.sh .venv/bin/python
```

> 必须用 `open DSH-FishBuddy.app` 启动。macOS 的 TCC 权限（麦克风 / 语音识别 / 屏幕录制）绑定在
> App Bundle 身份上，直接 `python main.py` 拿不到。

## 使用

| 想干什么 | 怎么做 |
|---|---|
| 说话 | 按住图标（或 `⌥Space`），说完松手 |
| 打字 | **双击图标**，或右键 →「打字说…」，或菜单栏 🐋 →「打字说…」 |
| 换形象/大小 | 右键 →「设置…」 |
| 陪看开关 | 右键 →「陪看」 |
| 让她看一眼 | 右键 →「让她看一眼」 |
| 退出 | 菜单栏 🐋 →「退出」 |

## 权限

| 权限 | 用于 | 缺失时表现 |
|---|---|---|
| 麦克风 | 按住说话 | 气泡提示无法打开麦克风 |
| 语音识别 | 所有转写 | 气泡提示去系统设置开启 |
| 屏幕录制 | 陪看、让她看一眼 | 气泡提供跳转设置的快捷入口 |
| 辅助功能 | 全局热键 | 热键无反应；图标仍可用 |

修改权限后需要**退出并重新启动**挂件。

## 配置

### 插件（`~/.dsh/fishbuddy-mac-plugin.json`）

```json
{
  "会话": "session-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "回调": "http://127.0.0.1:8778/hands/reply",
  "挂件路径": "/Applications/DSH-FishBuddy.app",
  "端口": 8777
}
```

这些值也可以在 **DSH → 设置 → 大肥鱼** 里改，那一页另有「启动挂件 / 打开挂件设置 / 露头 / 藏起来 / 自检」。

### 挂件（`~/.dsh/fishbuddy-mac.json`）

| 键 | 默认 | 含义 |
|---|---|---|
| `挂件` | `true` | 是否显示图标（菜单栏项始终存在） |
| `形象` | `image` | `image` / `minimal` / `mascot` |
| `尺寸` | `132` | 图标边长（48–320 px） |
| `朗读` | `true` | 是否朗读回话 |
| `音色` | `system` | `system` 或 `edge`（在线神经音色） |
| `麦克风` | `null` | 输入设备序号；`null` = 系统默认 |
| `弹幕` | `true` | 是否以弹幕呈现回话 |
| `弹幕字号` | `30` | 弹幕字号（16–56 px） |
| `弹幕字体` | `""` | 字体族；空 = 系统粗体 |
| `识别提示` | `""` | 逗号分隔的上下文词，提升专有名词准确率 |
| `陪看间隔` | `20` | 陪看截屏间隔（秒） |
| `热键表` | 见下 | 每个动作的按键绑定 |

默认热键：`⌥Space` 说话、`⌥P` 陪看开关、`⌥L` 看一眼、`⌥S` 设置。
绑定会校验：必须带修饰键；撞系统快捷键或与其它动作重复会被拒绝并提示原因。

## 架构

```
┌────────────────────────────┐        本机 HTTP            ┌──────────────────────────┐
│  DSH-FishBuddy.app         │                              │  DSH 插件                │
│  （PyObjC，附件型 App）     │  POST 8777/hands/say         │  dsh-fishbuddy-mac       │
│                            │  POST 8777/hands/frame  ───► │                          │
│  • NSWindow 悬浮层          │  POST 8777/hands/subtitle    │  • 会话投递              │
│  • SFSpeechRecognizer      │  GET  8777/hands/ping        │  • 回话捕获（过滤思考）   │
│  • AVSpeechSynthesizer     │                              │  • 设置页                │
│  • Vision OCR              │  POST 8778/hands/reply  ◄─── │  • 挂件控制              │
│  • sounddevice + numpy     │  POST 8778/settings|show|hide│                          │
└────────────────────────────┘                              └──────────────────────────┘
                                                                     │
                                                                     ▼
                                                             DSH 会话控制器
```

- **挂件**负责音频采集、识别、渲染与系统集成
- **插件**负责会话绑定、消息投递、回话捕获、设置界面

## 协议

| 方向 | 接口 | 负载 |
|---|---|---|
| 挂件 → 插件 | `POST /hands/say` | `{"text": "…"}` |
| 挂件 → 插件 | `POST /hands/frame` | `{"图片": "<base64>", "存档": 0\|1, "立即": 0\|1, "来源": "陪看"}` |
| 挂件 → 插件 | `POST /hands/subtitle` | `{"lines": ["…"]}` |
| 挂件 → 插件 | `GET /hands/ping` | — |
| 插件 → 挂件 | `POST /hands/reply` | `{"text": "…", "session": "session-…"}` |
| 插件 → 挂件 | `POST /settings` · `/show` · `/hide` | — |
| 插件 → 挂件 | `GET /state` | 版本、形象、麦克风状态、陪看状态 |

插件会把最近 30 秒抽到的台词拼在你说话的前面，这样 agent 不必多花一轮就能知道画面在演什么。

## 开发

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/ruff check .          # 静态检查
.venv/bin/python -m pytest -q   # 冒烟测试
./build.sh .venv/bin/python     # 构建 .app
python tools/make_assets.py     # 重新生成素材（需要 cairosvg）
```

目录：

```
main.py                 挂件：窗口、音频、识别、OCR、TTS、弹幕、设置、本地服务
plugin/                 DSH 插件：会话桥接、设置页、自检
tools/make_assets.py    素材生成（鲸鱼由 Twemoji SVG 转出，圆点自绘）
tests/                  冒烟测试
.github/workflows/      CI（ruff + pytest + 构建）与 Release（打包 + 校验和）
```

调试开关（环境变量，需 `launchctl setenv` 后 `open`）：

| 变量 | 作用 |
|---|---|
| `FISH_TEST_SHOT=1` | 启动时截一张图，验证屏幕录制权限 |
| `FISH_TEST_MIC=1` | 启动时录 1.5 秒并记录帧数 |
| `FISH_TEST_WAV=/p.wav` | 启动时转写指定音频并记录结果 |
| `FISH_TEST_SETTINGS=1` | 启动时直接打开设置窗口 |
| `FISH_TEST_MODE=minimal` | 强制使用某形象（不写回配置） |
| `FISH_TEST_REC=1` | 在主线程跑一次录音自测 |

## 发版

1. 更新 `main.py` 的 `VERSION`，在 `CHANGELOG.md` 记一笔
2. `git tag v0.x.y && git push origin v0.x.y`
3. Release Workflow 会校验 tag 与版本一致、跑测试、打包 zip 并附 SHA-256，发布 Release

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `No speech detected` | 输入电平过低（蓝牙耳机常见） | 设置里换麦克风，或靠近麦克风说话 |
| 专有名词总识别错 | 模型不认识 | 在「识别提示」里补词 |
| 截图为黑 | 屏幕录制被拒 | 重新授权并重启挂件 |
| 热键无效 | 辅助功能被拒 | 授权「大肥鱼」后重启 |
| 挂件看不见 | 被插件隐藏，或窗口在其它 Space | 菜单栏图标 → 设置 → 显示；窗口已设为加入所有 Space |
| 插件改了没生效 | DSH 会缓存插件模块 | 插件入口使用带时间戳的动态 import，重新启用即可 |

## 隐私与安全

- 语音、截图、字幕只在本机内存与 `~/.dsh` 下流转；截图落盘在 `~/.dsh/fishbuddy-frames`
- 插件路由经过 DSH 的信任栅栏（`connection.requestRejection`），并额外做回环 Host 兜底
- 唯一外发：选择「晓晓 · 在线」时，文本会发给 Microsoft Edge 语音服务

## 许可

代码（挂件 + 插件）采用 [MIT](LICENSE)。

素材**不属于 MIT**：官方鲸鱼标志归 DeepSeek 所有（本项目为非官方项目）；看板娘为 CC BY-NC-SA 4.0（禁止商用）。
详见 [THIRD-PARTY.md](THIRD-PARTY.md)。要再分发请替换 `assets/whale.png` 与 `assets/mascot.png`。
