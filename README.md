# 大肥鱼 · mac 挂件

[![CI](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml/badge.svg)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LosproeOcl/dsh-fishbuddy-mac?display_name=tag)](https://github.com/LosproeOcl/dsh-fishbuddy-mac/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%2013%2B-lightgrey)](#系统要求)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.12-blue)](requirements.txt)

<p align="center">
  <img src="assets/whale.png" width="150" alt="大肥鱼">
</p>

桌面上养一只鲸鱼：**按住说话**，话就进了 DSH 的那间会话；**她的回话**会浮成气泡，还能念出来。
想让她陪你一起看东西就开**陪看**，她会隔一会儿截一张你的屏幕。

> 这是 [dsh-fish-buddy](https://github.com/Yuuyuko-uu/dsh-fish-buddy)（Windows 版挂件）在 macOS 上的重做版。
> 只复用它**公开的插件协议**，UI 层照 AppKit 重写；**形象是我们自己画的**（`tools/make_assets.py`），
> 不含原项目的任何图片素材。

```
        ┌─────────────────┐
        │  她在说话…       │   ← 气泡（圆角/置顶/点击穿透）
        └────────┬────────┘
             🐋              ← 按住说话 · 拖动走位 · 双击打字 · 右键菜单
   ┌──────────────────────────────┐
   │ 陪看中 ● 已送 12 张 · 22:43:47 │   ← 陪看状态条
   └──────────────────────────────┘
```

---

## 目录

- [它能做什么](#它能做什么)
- [系统要求](#系统要求)
- [一键安装](#一键安装)
- [手动安装](#手动安装)
- [第一次运行：四个权限](#第一次运行四个权限)
- [接上 DSH](#接上-dsh)
- [怎么用](#怎么用)
- [设置](#设置)
- [两种形象](#两种形象)
- [配置文件](#配置文件)
- [它和 DSH 之间说什么](#它和-dsh-之间说什么)
- [开发](#开发)
- [发版](#发版)
- [常见问题](#常见问题)
- [许可与致谢](#许可与致谢)

---

## 它能做什么

| 功能 | 说明 | 需要什么权限 |
|---|---|---|
| **按住说话** | 按住鲸鱼说话 → 本机中文语音识别 → 送进绑定的会话 | 麦克风、语音识别 |
| **回话气泡** | 她这一轮最后那段话，浮在鲸鱼上方，10 秒后自己消失 | — |
| **念出来** | 用系统语音把回话读出来（中文 Tingting，不联网），可关 | — |
| **全局热键** | 默认 `⌥Space` 按住说话，**可以自己改**，撞系统快捷键会提示 | 辅助功能（可选） |
| **陪看** | 每 20 秒截一张屏，**攒着**等说话时一起给她看，不打扰 | 屏幕录制 |
| **让她看一眼** | 立刻截一张并叫醒她 | 屏幕录制 |
| **两种形象** | 素材形象（鲸鱼）/ 极简圆点（安静不抢眼） | — |
| **设置窗口** | 挂件开关、形象、热键、朗读、陪看间隔，改完即生效 | — |
| **打字说** | 双击鲸鱼，弹输入框 | — |
| **拖动 / 置顶** | 鲸鱼浮在所有窗口上、不抢焦点、拖着走 | — |

**还没做**：磨砂背景、陪看字幕（从系统音频/画面抽台词）、弹幕框、电话式双向语音。

## 系统要求

- macOS 13 或更新（在 26 上实测）
- Apple Silicon 或 Intel（`pyobjc` 两个架构都有 wheel）
- Python **3.9+**（CI 跑 3.9 和 3.12；本机实测 3.14 也可以）
- 已装 DSH，并能装插件（`dsh plugin ...`）
- 磁盘：约 200 MB（venv + 依赖；语音识别用的是系统能力，不额外下模型）

## 一键安装

```sh
git clone https://github.com/LosproeOcl/dsh-fishbuddy-mac.git
cd dsh-fishbuddy-mac
./install.sh            # 建 .venv → 装依赖 → 生成 DSH-FishBuddy.app
open DSH-FishBuddy.app
```

想指定 Python：`./install.sh /opt/homebrew/bin/python3.12`

装完先别急着说话，去下一节把权限给了。

## 手动安装

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

./build.sh                       # 生成 DSH-FishBuddy.app（内嵌你的 python 绝对路径）
open DSH-FishBuddy.app
```

> 一定要用 `open DSH-FishBuddy.app` 启动。系统的麦克风 / 语音识别 / 屏幕录制权限是**按 .app 身份**发和记的，
> 直接 `python main.py` 跑，权限对不上，会一直被拒。

## 第一次运行：四个权限

系统设置 → 隐私与安全性：

| 权限 | 用途 | 不给会怎样 |
|---|---|---|
| **麦克风** | 按住说话 | 气泡提示"开不了麦克风" |
| **语音识别** | 说话转文字 | 气泡提示去设置里打开 |
| **屏幕录制** | 陪看 / 让她看一眼 | 气泡提示（右键菜单可直接跳转设置） |
| **辅助功能** | 全局热键（可选） | 热键没反应，但按住鲸鱼照样能用 |

改完权限要**退出挂件重开**才生效（右键 → 退出，或菜单栏 🐋 → 退出）。

## 接上 DSH

挂件只负责"听/看/说"，真正陪你聊的是 DSH 那间会话。所以要装 DSH 插件：

```sh
dsh plugin --profile desktop add dsh-fish-buddy
```

然后让插件知道**送到哪一间**、**回话递到哪**。编辑 `~/.dsh/fish-buddy-config.json`：

```json
{
  "总开关": true,
  "端口": 8777,
  "会话": "session-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "回调": "http://127.0.0.1:8778/hands/reply",
  "自动开挂件": false,
  "回话端口": 8778
}
```

- `会话`：DSH 里的会话 id（在 `~/.dsh/sessions/<工作区>/` 下能看到目录名），也可以去 **DSH 设置 → 鱼搭子 → 送到哪一间** 里选
- `回调`：挂件监听 `8778`，插件把回话 POST 回来
- `自动开挂件`：**必须关掉**——那个逻辑找的是 Windows 的 `.exe`

装完重启一次 DSH。

## 怎么用

| 想干什么 | 怎么做 |
|---|---|
| 说一句 | **按住鲸鱼** → 说 → 松手（或按住热键） |
| 打字 | **双击鲸鱼** → 输入 → 发送 |
| 挪位置 | 按住拖走（移动超过 5px 就自动取消这次录音） |
| 打开设置 | 右键 → 设置…（或菜单栏 🐋 → 设置…） |
| 开/关陪看 | 右键 → 陪看 |
| 让她看一眼 | 右键 → 让她看一眼 |
| 关掉朗读 | 右键 → 念出来 |
| 测 DSH 通不通 | 右键 → 打个招呼 |
| 退出 | 右键 → 退出 / 菜单栏 🐋 |

## 设置

右键 → **设置…**，一共五项，改完立刻生效、自动记住：

| 项 | 说明 |
|---|---|
| **显示挂件** | 关掉后桌面上不占地方，只留菜单栏 🐋（设置还在） |
| **形象** | `素材形象` = 那只鲸鱼；`极简圆点` = 一个小圆点 |
| **全局热键** | 点一下按钮，按下你想用的组合键即可；**太素（不带 ⌘/⌥/⌃）或撞系统快捷键会被拒绝并说明原因** |
| **念出来** | 她的回话用系统语音读出来 |
| **陪看间隔** | 10–120 秒，默认 20 |

热键冲突检测覆盖：Spotlight、切换输入法、Finder 搜索、切换 App、退出 App、⌘⇧3/4/5 截屏、调度中心等。
macOS 不提供"查询所有 App 占用的快捷键"的接口，所以这层是**常见系统快捷键的静态表 + 基本规则**，
剩下的撞车靠你自己判断；撞了就再换一个。

## 两种形象

| 素材形象 | 极简圆点 |
|---|---|
| ![](assets/whale.png) | ![](assets/dot.png) |
| 128px 的鲸鱼 | 36px 的小圆点，安静、不抢眼；说话时会轻微放大 |

两者都是**本仓库自己画的**（`tools/make_assets.py`，MIT），想换成自己的图就覆盖 `assets/whale.png` / `assets/dot.png`。

## 配置文件

挂件自己的设置存在 `~/.dsh/fishbuddy-mac.json`：

```json
{
  "挂件": true,
  "形象": "image",
  "朗读": true,
  "热键": true,
  "键": 49,
  "修饰": 524288,
  "陪看间隔": 20
}
```

- `键` 是 macOS 的 keyCode（49 = 空格），`修饰` 是修饰键位掩码（524288 = ⌥）
- 一般不用手改，设置窗口会写这个文件

## 它和 DSH 之间说什么

挂件 ⇄ DSH 插件，全在本机回环上：

| 方向 | 接口 | 报文 |
|---|---|---|
| 挂件 → 插件 | `POST 127.0.0.1:8777/hands/say` | `{"text": "说了什么"}` |
| 挂件 → 插件 | `POST 127.0.0.1:8777/hands/frame` | `{"图片": "<base64 jpeg>", "存档": 1, "立即": 0, "来源": "陪看"}` |
| 挂件 → 插件 | `GET 127.0.0.1:8777/hands/ping` | — |
| 插件 → 挂件 | `POST 127.0.0.1:8778/hands/reply` | `{"text": "她的回话", "session": "session-…"}` |

- `存档=1`：只攒着，不叫醒（陪看用）
- `立即=1`：立刻发一轮（"让她看一眼"用）
- 两个都不带：排进字幕队列，跟下一批一起发

## 开发

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/ruff check .          # lint
.venv/bin/python -m pytest -q   # 测试
./build.sh .venv/bin/python     # 构建 .app
python tools/make_assets.py     # 重新生成形象素材
```

目录：

```
main.py                  全部逻辑（窗口 / 录音 / 识别 / 陪看 / 热键 / 设置窗口 / TTS / 回话服务）
build.sh                 生成 DSH-FishBuddy.app
install.sh               一键装
tools/make_assets.py     画形象素材（原创）
tests/test_basic.py      冒烟测试
assets/                  whale.png / dot.png / whale.svg（都是自己画的）
.github/workflows/       CI 与发版
```

调试小开关（环境变量）：

| 变量 | 作用 |
|---|---|
| `FISH_TEST_MIC=1` | 启动后录 1.5 秒，结果写 `mic.log` |
| `FISH_TEST_SHOT=1` | 启动后截一张存 `shot.png`，验屏幕录制权限 |
| `FISH_TEST_WAV=/path.wav` | 启动后识别这个 wav，结果写 `asr.log` |
| `FISH_TEST_SETTINGS=1` | 启动后自动打开设置窗口 |
| `FISH_TEST_MODE=minimal` | 强制用极简形象启动（不写回配置） |

> 这些开关要走 `launchctl setenv` 再 `open` 才会被 .app 读到。

## 发版

1. 改 `main.py` 里的 `VERSION`，在 `CHANGELOG.md` 里记一笔
2. `git commit` 之后打 tag：`git tag v0.4.0 && git push origin v0.4.0`
3. `Release` workflow 会：**校验 tag 和 VERSION 一致** → 跑测试 → 打 zip + sha256 → 发 Release

手动发版：Actions → Release → Run workflow，填 tag。

## 常见问题

**按住没反应？** 先看麦克风权限；如果 `mic.log` 里有帧数，那就是识别没返回，检查语音识别权限。

**截屏一直是黑的 / 报 `could not create image from display`？** 屏幕录制权限没给，或者给了但没重启挂件。

**热键没反应？** 辅助功能权限。设置窗口里点「打开辅助功能设置」，勾上后**重开挂件**。

**改热键时一直提示冲突？** 说明这个组合被系统占了，换一个带 ⌥ 或 ⌃ 的组合。

**鲸鱼不见了？** 设置里「显示挂件」被关了，点菜单栏 🐋 → 设置… 打开，或者退出重开。

**DSH 那边报「那间会话没开着」？** 会话 id 不对，或者那间会话在 DSH 里没打开过。

**说完没反应，但气泡提示"没绑会话"？** `~/.dsh/fish-buddy-config.json` 里 `会话` 是空的。

## 许可与致谢

代码与形象素材都用 [MIT](LICENSE)，形象由 `tools/make_assets.py` 生成，可自由修改再分发。

设计思路与协议来自 [Yuuyuko-uu/dsh-fish-buddy](https://github.com/Yuuyuko-uu/dsh-fish-buddy)（插件许可 1.2）。
**本仓库不包含该项目的源代码与图片素材**——它 README 里写明角色图、气泡框等素材不单独授权二次使用。
