# dsh-fishbuddy-mac（DSH 插件）

mac 挂件的另一半：把挂件说的话送进你选的那间会话，把她最后的回话递回挂件，
并在 **DSH 设置 → 大肥鱼** 里提供「启动挂件 / 打开挂件设置 / 让挂件露头」。

替代原版 `dsh-fish-buddy`（那半边只认 Windows 的 exe；这个只认 mac 挂件）。

## 装

```sh
dsh plugin --profile desktop add ./plugin      # 或把这个目录拷到任意位置后 add
```

装完重启 DSH；设置里会出现「大肥鱼」。

## 配置

`~/.dsh/fishbuddy-mac-plugin.json`

```json
{
  "会话": "session-xxxx",
  "回调": "http://127.0.0.1:8778/hands/reply",
  "挂件路径": "/Applications/DSH-FishBuddy.app",
  "端口": 8777
}
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/hands/ping` | 活着吗 |
| POST | `/hands/say` | `{"text":"…"}` → 送进会话 |
| POST | `/hands/frame` | `{"图片":"<base64>","立即":0/1,"来源":"陪看"}` |

设置页接口都在 `/dsh-fishbuddy/api/*`（走 DSH 自己的登录态与信任栅栏）。

## 和挂件的配合

挂件默认往 `127.0.0.1:8777` 说话、在 `127.0.0.1:8778` 收话；
设置页的「打开挂件设置」会 `POST http://127.0.0.1:8778/settings`，挂件收到就把设置窗口弹出来。
