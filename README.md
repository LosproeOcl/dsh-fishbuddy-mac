# 大肥鱼 · mac 挂件

把 [dsh-fish-buddy](https://github.com/Yuuyuko-uu/dsh-fish-buddy) 的**陪聊挂件**在 macOS 上重做的一版。
用的是它公开的插件协议（`127.0.0.1:8777`），DSH 那半边不用改。

> ⚠️ 这个仓库**不含**原项目的任何图片素材（原作者的鲸鱼图、气泡框不单独授权二次使用）。
> 想换形象：放一张自己的 `assets/whale.png`（正方形、带透明通道）即可；没有就用一个蓝色圆底。
>
> 设计思路来自原项目，代码是照着 mac 的 AppKit 重写的；协议格式参考原仓库 README。

## 现在能做什么

- 桌面上浮着一只鲸鱼：无边框、置顶、可拖动、不抢焦点
- **按住鲸鱼说话** → macOS 本机语音识别（`SFSpeechRecognizer`，中文，可离线）→ 送进绑定的会话
- **她的回话**经本机 `8778` 口递回来 → 鲸鱼上方弹气泡
- **双击** → 打字说；**右键** → 陪看开关 / 让她看一眼 / 打开屏幕录制设置 / 打个招呼 / 退出
- **陪看**：每 20 秒截一张屏，攒着等说话时一起给她看；「让她看一眼」是立刻叫醒她
- 菜单栏 🐋 可退出

## 装

```sh
python3 -m venv .venv
.venv/bin/pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-Speech sounddevice numpy pillow
./build.sh
open DSH-FishBuddy.app
```

> 一定要用 `open` 启动：麦克风 / 语音识别 / 屏幕录制这几个权限是**按 .app 身份**给的，
> 直接 `python main.py` 拿不到。

## 权限

| 权限 | 用途 | 没给会怎样 |
|---|---|---|
| 麦克风 | 按住说话 | 气泡提示开不了麦克风 |
| 语音识别 | 说话转文字 | 气泡提示去系统设置打开 |
| 屏幕录制 | 陪看截图 | 气泡提示 + 右键菜单里能直接跳设置 |

改完权限要**退出挂件重开**才生效。

## 接上 DSH

装 DSH 插件：

```sh
dsh plugin --profile desktop add dsh-fish-buddy
```

然后 `~/.dsh/fish-buddy-config.json`：

```json
{
  "会话": "session-xxxx",
  "回调": "http://127.0.0.1:8778/hands/reply",
  "自动开挂件": false
}
```

或者去 DSH 设置 → 鱼搭子 里选。`自动开挂件` 要关掉：那个逻辑找的是 Windows 的 exe。

## 协议（我用到的）

```
POST 127.0.0.1:8777/hands/say    {"text":"…"}
POST 127.0.0.1:8777/hands/frame  {"图片":"<base64>","存档":1,"立即":0,"来源":"陪看"}
GET  127.0.0.1:8777/hands/ping
POST 127.0.0.1:8778/hands/reply  {"text":"她的回话"}   ← 插件推给我
```

## 还没做

- 全局热键（现在只能按住鲸鱼 / 双击）
- 磨砂背景（`NSVisualEffectView`）
- 陪看字幕（从系统音频或画面 OCR 抽台词）
- 弹幕框、电话式双向语音

## 许可

代码 MIT。不带原项目素材，也不包含它的代码。
