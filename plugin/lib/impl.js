/**
 * dsh-fishbuddy-mac —— 宿主半边
 *
 * 干什么：
 *   1. 在本机 127.0.0.1:8777 收挂件说的话（/hands/say）和截图（/hands/frame）
 *   2. 把话送进你绑定的那间会话；一轮说完，把最后那段回话 POST 回挂件（默认 8778）
 *   3. 设置页接口：状态、会话列表、自检、启动挂件、打开挂件设置、露头/藏起来
 *   4. 设置页 UI 在 lib/client.js
 *
 * 配置：~/.dsh/fishbuddy-mac-plugin.json
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import http from 'node:http'
import { execFile } from 'node:child_process'

const HOME = process.env.HOME || os.homedir()
const DSH_HOME = process.env.DSH_HOME || path.join(HOME, '.dsh')
const CONFIG_PATH = path.join(DSH_HOME, 'fishbuddy-mac-plugin.json')
const DEFAULT_APP = path.join(HOME, '.dsh', 'whale-work', 'fishbuddy-mac', 'DSH-FishBuddy.app')

const VERSION = '0.10.4'

const DEFAULT_CONFIG = {
  会话: '',
  回调: 'http://127.0.0.1:8778/hands/reply',
  挂件路径: DEFAULT_APP,
  端口: 8777,
}

function readConfig() {
  try {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'))
    return { ...DEFAULT_CONFIG, ...raw }
  } catch {
    return { ...DEFAULT_CONFIG }
  }
}

function writeConfig(next) {
  fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true })
  const tmp = CONFIG_PATH + '.' + process.pid + '.tmp'
  fs.writeFileSync(tmp, JSON.stringify(next, null, 2) + '\n')
  fs.renameSync(tmp, CONFIG_PATH)
}

function json(res, code, obj) {
  const body = JSON.stringify(obj)
  res.statusCode = code
  res.setHeader('content-type', 'application/json; charset=utf-8')
  res.setHeader('content-length', Buffer.byteLength(body))
  res.end(body)
}

async function readBody(req, limit = 12 * 1024 * 1024) {
  let size = 0
  const chunks = []
  for await (const c of req) {
    size += c.length
    if (size > limit) throw new Error('body too large')
    chunks.push(c)
  }
  if (!chunks.length) return {}
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'))
  } catch {
    return {}
  }
}

function isReasoning(part) {
  if (!part || typeof part !== 'object') return false
  const t = String(part.type || '').toLowerCase()
  if (t.includes('reason') || t.includes('think') || t.includes('analysis') || t.includes('summary')) {
    return true
  }
  return Boolean(part.reasoning || part.thinking || part.redacted_reasoning)
}

/** 只要真正的回复正文：思考 / 推理 / 摘要片段一律丢掉 */
export function textOf(message) {
  const content = message?.content ?? message?.parts ?? []
  const parts = Array.isArray(content) ? content : [content]
  return parts
    .filter((p) => typeof p === 'string' || !isReasoning(p))
    .map((p) => {
      if (typeof p === 'string') return p
      if (p && typeof p.text === 'string') return p.text
      return ''
    })
    .join('')
    .trim()
}

export default {
  name: 'dsh-fishbuddy-mac',
  inject: ['sessionController', 'webServer', 'connection'],

  apply(ctx) {
    const log = (...a) => console.log('[fishbuddy-mac]', ...a)
    const state = {
      lastReply: '',
      lastReplyAt: 0,
      says: 0,
      frames: 0,
      serverOk: false,
      serverErr: '',
      startedAt: Date.now(),
      events: [],
    }
    const pending = new Map()
    const subtitles = []   // {at, text} —— 陪看抽到的台词，说话时一起带过去

    function note(kind, text) {
      state.events.push({ at: Date.now(), kind, text: String(text ?? '').slice(0, 120) })
      if (state.events.length > 40) state.events.shift()
    }

    function rejected(req, res) {
      try {
        const conn = ctx.get('connection') || ctx.connection
        if (conn && typeof conn.requestRejection === 'function') {
          const code = conn.requestRejection(req)
          if (code === undefined || code === null || code === false) return false
          res.statusCode = typeof code === 'number' ? code : 403
          res.end()
          return true
        }
      } catch {
        /* fail-closed below */
      }
      const host = String(req.headers?.host ?? '').toLowerCase()
      const name = host.startsWith('[') ? host.slice(0, host.indexOf(']') + 1) : host.split(':')[0]
      if (name === '127.0.0.1' || name === 'localhost' || name === '[::1]') return false
      json(res, 403, { ok: false, error: '不受信任的来源' })
      return true
    }

    const routes = []
    function route(method, pathname, handler) {
      const dispose = ctx.webServer.register({
        kind: 'exact',
        path: pathname,
        handler: async (req, res) => {
          if (rejected(req, res)) return
          if (method && String(req.method).toUpperCase() !== method) {
            return json(res, 405, { ok: false, error: 'method not allowed' })
          }
          try {
            await handler(req, res)
          } catch (e) {
            json(res, 500, { ok: false, error: String(e?.message ?? e) })
          }
        },
      })
      routes.push(dispose)
    }

    // ---------- 会话 ----------
    function listSessions() {
      const root = path.join(DSH_HOME, 'sessions')
      const cacheRoot = path.join(DSH_HOME, 'storages', 'session_projcache', 'sessions')
      const out = []
      let dirs = []
      try {
        dirs = fs.readdirSync(root, { withFileTypes: true }).filter((d) => d.isDirectory())
      } catch {
        return out
      }
      for (const ws of dirs) {
        let ids = []
        try {
          ids = fs
            .readdirSync(path.join(root, ws.name), { withFileTypes: true })
            .filter((d) => d.isDirectory())
        } catch {
          continue
        }
        for (const id of ids) {
          const file = path.join(root, ws.name, id.name, 'session.v4.jsonl.zstd')
          let st
          try {
            st = fs.statSync(file)
          } catch {
            continue
          }
          let title = ''
          try {
            const c = JSON.parse(fs.readFileSync(path.join(cacheRoot, id.name + '.json'), 'utf8'))
            title = String(c?.record?.rows?.title?.val ?? '')
          } catch {
            /* 没缓存就没有标题 */
          }
          out.push({ id: id.name, workspace: ws.name, title, mtime: st.mtimeMs })
        }
      }
      out.sort((a, b) => b.mtime - a.mtime)
      return out.slice(0, 80)
    }

    /** 最近 30 秒的台词，拼在正文前面（陪看时她才知道刚才画面在说什么） */
    function withSubtitles(text) {
      const cut = Date.now() - 30_000
      const recent = subtitles.filter((x) => x.at >= cut).slice(-6)
      if (!recent.length) return text
      const line = recent.map((x) => x.text).join(' / ')
      return `（刚才画面字幕：${line}）\n${text}`
    }

    /** 绑定会话不存在时，退到最近活跃的那间（并在返回里带上标题） */
    function resolveSession(requested) {
      const list = listSessions()
      const want = String(requested || '').trim()
      const hit = want ? list.find((x) => x.id === want) : null
      if (hit) return { id: hit.id, title: hit.title || hit.id, fallback: false }
      if (list.length) return { id: list[0].id, title: list[0].title || list[0].id, fallback: !!want }
      throw new Error('磁盘上没有任何会话')
    }

    async function deliver(text, sessionId) {
      const controller = ctx.get('sessionController') || ctx.sessionController
      if (!controller) throw new Error('sessionController 不可用')
      const picked = resolveSession(String(sessionId || readConfig().会话 || '').trim())
      const target = picked.id
      if (picked.fallback) {
        note('session-fallback', '绑定会话不在磁盘上，改送最近活跃：' + picked.title)
      }
      try {
        await controller.create({ sessionId: target, cwd: process.cwd() })
      } catch {
        /* 已存在就继续 */
      }
      pending.delete(target)
      const ac = new AbortController()
      await controller.prompt(
        {
          requestId: 'fishbuddy-' + Date.now(),
          sessionId: target,
          mode: 'queue',
          content: [{ type: 'text', text }],
        },
        ac.signal,
      )
      state.says += 1
      note('say', text)
      return { id: target, title: picked.title, fallback: picked.fallback }
    }

    // ---------- 挂件 ----------
    function widgetBase() {
      const cfg = readConfig()
      return String(cfg.回调 || '').replace(/\/hands\/reply.*$/, '') || 'http://127.0.0.1:8778'
    }

    async function widgetState() {
      try {
        const r = await fetch(widgetBase() + '/state', { signal: AbortSignal.timeout(1500) })
        if (!r.ok) throw new Error('HTTP ' + r.status)
        return { ok: true, ...(await r.json()) }
      } catch (e) {
        return { ok: false, error: String(e?.message ?? e) }
      }
    }

    async function widgetCall(p) {
      const r = await fetch(widgetBase() + p, {
        method: 'POST',
        signal: AbortSignal.timeout(2500),
      })
      return { ok: r.ok, 说: (await r.text()).slice(0, 200) }
    }

    async function pushReply(text) {
      const cfg = readConfig()
      if (!cfg.回调 || !text) return
      try {
        const r = await fetch(cfg.回调, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ text }),
        })
        if (!r.ok) throw new Error('HTTP ' + r.status)
        state.lastReply = text
        state.lastReplyAt = Date.now()
        note('reply', text)
      } catch (e) {
        note('reply-error', String(e?.message ?? e))
        log('回话没递到挂件：', e?.message ?? e)
      }
    }

    const off = ctx.on('session/event', (session, event) => {
      const cfg = readConfig()
      const sid = String(session?.id ?? '')
      if (!sid || sid !== String(cfg.会话 ?? '')) return
      const type = event?.type
      const data = event?.data ?? {}
      if (type === 'assistant/message') {
        if (data.interrupted) return
        const t = textOf(data.message)
        if (t) pending.set(sid, { turn: data.turn, text: t })
        return
      }
      if (type === 'turn/end') {
        const done = data?.reason?.kind === 'completed'
        const got = pending.get(sid)
        pending.delete(sid)
        if (!done || !got || got.turn !== data.turn) return
        void pushReply(got.text)
      }
    })
    ctx.effect(() => () => {
      try {
        off?.()
      } catch {
        /* ignore */
      }
    })

    // 8777：挂件说话 / 截图
    let server = null
    function startWidgetServer() {
      const cfg = readConfig()
      const port = Number(cfg.端口) || 8777
      server = http.createServer(async (req, res) => {
        const p = String(req.url || '/').split('?')[0]
        if (req.method === 'GET' && (p === '/hands/ping' || p === '/ping')) {
          return json(res, 200, { ok: true, 说: '大肥鱼插件在这儿', 版本: VERSION })
        }
        if (req.method !== 'POST') return json(res, 405, { ok: false, 说: '要 POST' })
        try {
          if (p === '/hands/say' || p === '/say') {
            const body = await readBody(req)
            let text = String(body.text ?? body.正文 ?? '').trim()
            if (!text) return json(res, 400, { ok: false, 说: '空的' })
            text = withSubtitles(text)
            const sent = await deliver(text, body.session)
            return json(res, 200, {
              ok: true,
              说: '送进去了',
              会话: sent.id,
              标题: sent.title,
              回落: sent.fallback,
            })
          }
          if (p === '/hands/subtitle' || p === '/subtitle') {
            const body = await readBody(req)
            const lines = Array.isArray(body.lines) ? body.lines : (body.text ? [body.text] : [])
            const nowMs = Date.now()
            for (const one of lines.slice(0, 20)) {
              const t = String(typeof one === 'string' ? one : (one && (one.text || one["文"])) || '').trim()
              if (t) subtitles.push({ at: nowMs, text: t.slice(0, 120) })
            }
            while (subtitles.length > 60) subtitles.shift()
            return json(res, 200, { ok: true, 说: '收到 ' + lines.length + ' 句' })
          }
          if (p === '/hands/frame' || p === '/frame') {
            const body = await readBody(req)
            const b64 = String(body.图片 ?? '')
            if (!b64) return json(res, 400, { ok: false, 说: '没带图' })
            const dir = path.join(DSH_HOME, 'fishbuddy-frames')
            fs.mkdirSync(dir, { recursive: true })
            const file = path.join(dir, `frame-${Date.now()}.jpg`)
            fs.writeFileSync(file, Buffer.from(b64, 'base64'))
            state.frames += 1
            note('frame', `${Math.round(Buffer.byteLength(b64, 'base64') / 1024)}KB`)
            if (Number(body.立即) === 1) {
              const head = `（挂件截了一张屏：${file}）` + (body.来源 ? ` 来源：${body.来源}` : '')
              await deliver(withSubtitles(head))
              return json(res, 200, { ok: true, 说: '发了，等她说' })
            }
            return json(res, 200, { ok: true, 说: '存着了', 存: file })
          }
          return json(res, 404, { ok: false, 说: '没有这个口子' })
        } catch (e) {
          return json(res, 500, { ok: false, 说: String(e?.message ?? e) })
        }
      })
      let retry = 0
      server.on('error', (e) => {
        state.serverOk = false
        state.serverErr = String(e?.message ?? e)
        const busy = String(e?.code || '') === 'EADDRINUSE'
        log('挂件口子起不来：', state.serverErr)
        if (busy && retry < 60) {
          retry += 1
          setTimeout(() => {
            try {
              server.listen(port, '127.0.0.1')
            } catch {
              /* ignore */
            }
          }, 5000)
        }
      })
      server.listen(port, '127.0.0.1', () => {
        state.serverOk = true
        state.serverErr = ''
        log(`挂件口子开着：127.0.0.1:${port}`)
      })
    }
    ctx.effect(() => {
      startWidgetServer()
      // 关掉插件时要真的把口子释放，不然重新启用会一直 EADDRINUSE
      return () => {
        try {
          server?.close()
        } catch {
          /* ignore */
        }
        server = null
      }
    })

    // ---------- 设置页接口 ----------
    route('GET', '/dsh-fishbuddy/api/state', async (req, res) => {
      const cfg = readConfig()
      const widget = await widgetState()
      json(res, 200, {
        ok: true,
        version: VERSION,
        config: cfg,
        server: { ok: state.serverOk, error: state.serverErr, port: cfg.端口 },
        widget,
        counts: { says: state.says, frames: state.frames },
        lastReply: state.lastReply,
        lastReplyAt: state.lastReplyAt,
        uptimeSec: Math.round((Date.now() - state.startedAt) / 1000),
        events: state.events.slice(-12),
      })
    })

    route('GET', '/dsh-fishbuddy/api/sessions', async (req, res) => {
      json(res, 200, { ok: true, sessions: listSessions() })
    })

    route('POST', '/dsh-fishbuddy/api/config', async (req, res) => {
      const body = await readBody(req)
      const next = readConfig()
      for (const k of ['会话', '回调', '挂件路径']) {
        if (typeof body[k] === 'string') next[k] = body[k].trim()
      }
      if (Number(body.端口) > 0) next.端口 = Number(body.端口)
      writeConfig(next)
      note('config', '保存配置')
      json(res, 200, { ok: true, config: next })
    })

    // 自检：一条一条查，返回 checklist
    route('POST', '/dsh-fishbuddy/api/doctor', async (req, res) => {
      const cfg = readConfig()
      const checks = []
      const push = (name, ok, detail) => checks.push({ name, ok, detail })

      push('配置文件', fs.existsSync(CONFIG_PATH), CONFIG_PATH)
      push('挂件口子', state.serverOk, state.serverOk ? `127.0.0.1:${cfg.端口}` : state.serverErr)

      const w = await widgetState()
      push('挂件在线', !!w.ok, w.ok ? `版本 ${w.version || '?'}` : String(w.error || '没应答'))
      if (w.ok) {
        push('挂件形象', true, w["形象"] === 'minimal' ? '极简圆点' : '素材形象')
        push('陪看', true, w.watching ? '开着' : '关着')
      }

      const app = String(cfg.挂件路径 || '')
      push('挂件 App', !!app && fs.existsSync(app), app || '没填')

      const sid = String(cfg.会话 || '')
      const hit = listSessions().find((x) => x.id === sid)
      push('绑定会话', !!hit, hit ? hit.title || hit.id : sid ? sid + '（磁盘上没找到）' : '还没选')

      push('回调地址', /^http:\/\/127\.0\.0\.1:\d+\//.test(String(cfg.回调)), String(cfg.回调))

      json(res, 200, { ok: true, checks })
    })

    route('POST', '/dsh-fishbuddy/api/launch', async (req, res) => {
      const app = String(readConfig().挂件路径 || '')
      if (!app || !fs.existsSync(app)) {
        return json(res, 200, { ok: false, 说: '找不到挂件：在设置里填 .app 的完整路径' })
      }
      execFile('open', ['-a', app], (err) => {
        if (err) return json(res, 200, { ok: false, 说: String(err.message) })
        json(res, 200, { ok: true, 说: '挂件起来了' })
      })
    })

    route('POST', '/dsh-fishbuddy/api/open-widget-settings', async (req, res) => {
      try {
        json(res, 200, { ok: true, ...(await widgetCall('/settings')) })
      } catch (e) {
        json(res, 200, { ok: false, 说: '挂件没在跑：' + String(e?.message ?? e) })
      }
    })

    route('POST', '/dsh-fishbuddy/api/show-widget', async (req, res) => {
      try {
        json(res, 200, { ok: true, ...(await widgetCall('/show')) })
      } catch (e) {
        json(res, 200, { ok: false, 说: String(e?.message ?? e) })
      }
    })

    route('POST', '/dsh-fishbuddy/api/hide-widget', async (req, res) => {
      try {
        json(res, 200, { ok: true, ...(await widgetCall('/hide')) })
      } catch (e) {
        json(res, 200, { ok: false, 说: String(e?.message ?? e) })
      }
    })

    route('POST', '/dsh-fishbuddy/api/say', async (req, res) => {
      const body = await readBody(req)
      const text = String(body.text ?? '').trim()
      if (!text) return json(res, 400, { ok: false, error: '空的' })
      await deliver(text)
      json(res, 200, { ok: true })
    })

    ctx.effect(() => () => {
      for (const d of routes) {
        try {
          d?.()
        } catch {
          /* ignore */
        }
      }
    })

    log(`配置：${CONFIG_PATH}`)
  },
}
