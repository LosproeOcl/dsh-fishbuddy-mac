/**
 * dsh-fishbuddy-mac —— 宿主半边
 *
 * 干的四件事：
 *   1. 在本机开 127.0.0.1:8777，收挂件说的话（/hands/say）和截图（/hands/frame）
 *   2. 把话送进你绑定的那间会话；一轮说完，把最后那段回话 POST 回挂件（默认 8778）
 *   3. 设置页接口：读写配置、列会话、启动挂件、打开挂件设置
 *   4. 设置页 UI 在 lib/client.js
 *
 * 配置：~/.dsh/fishbuddy-mac-plugin.json
 *   { "会话": "session-…", "回调": "http://127.0.0.1:8778/hands/reply",
 *     "挂件路径": "/Users/you/Applications/DSH-FishBuddy.app", "端口": 8777 }
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

/** 从 message.content 里把文字抠出来 */
function textOf(message) {
  const content = message?.content ?? message?.parts ?? []
  const parts = Array.isArray(content) ? content : [content]
  return parts
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
    const state = { lastReply: '', frames: 0, says: 0, serverOk: false, serverErr: '' }
    const pending = new Map() // sessionId -> { turn, text }

    // ---------- 信任栅栏：只允许本机 / DSH 认可的来源 ----------
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
        /* 落到下面 fail-closed */
      }
      // 栅栏不可用：只放行回环 Host
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

    // ---------- 会话投递 ----------
    async function deliver(text, sessionId) {
      const controller = ctx.get('sessionController') || ctx.sessionController
      if (!controller) throw new Error('sessionController 不可用')
      const target = String(sessionId || readConfig().会话 || '').trim()
      if (!target) throw new Error('还没绑会话：设置 → 大肥鱼 → 送到哪一间')
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
      return target
    }

    // ---------- 回话递回挂件 ----------
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
      } catch (e) {
        log('回话没递到挂件：', e?.message ?? e)
      }
    }

    // 一轮说完 → 把最后那段回话递回去
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
        state.lastReply = got.text
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

    // ---------- 挂件那半边：8777 ----------
    let server = null
    function startWidgetServer() {
      const cfg = readConfig()
      const port = Number(cfg.端口) || 8777
      server = http.createServer(async (req, res) => {
        const p = String(req.url || '/').split('?')[0]
        if (req.method === 'GET' && (p === '/hands/ping' || p === '/ping')) {
          return json(res, 200, { ok: true, 说: '大肥鱼插件在这儿' })
        }
        if (req.method !== 'POST') return json(res, 405, { ok: false, 说: '要 POST' })
        try {
          if (p === '/hands/say' || p === '/say') {
            const body = await readBody(req)
            const text = String(body.text ?? body.正文 ?? '').trim()
            if (!text) return json(res, 400, { ok: false, 说: '空的' })
            await deliver(text, body.session)
            return json(res, 200, { ok: true, 说: '送进去了' })
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
            const immediate = Number(body.立即) === 1
            if (immediate) {
              const cfg2 = readConfig()
              await deliver(`（挂件截了一张屏：${file}）` + (body.来源 ? ` 来源：${body.来源}` : ''),
                cfg2.会话)
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
        // 端口被别的插件占着（比如装过原版 dsh-fish-buddy）→ 隔一会儿再试
        if (busy && retry < 60) {
          retry += 1
          setTimeout(() => {
            try {
              server.listen(port, '127.0.0.1')
            } catch {}
          }, 5000)
        }
      })
      server.listen(port, '127.0.0.1', () => {
        state.serverOk = true
        state.serverErr = ''
        log(`挂件口子开着：127.0.0.1:${port}`)
      })
      return () => {
        try {
          server?.close()
        } catch {
          /* ignore */
        }
      }
    }
    ctx.effect(() => startWidgetServer())

    // ---------- 设置页接口 ----------
    route('GET', '/dsh-fishbuddy/api/state', async (req, res) => {
      const cfg = readConfig()
      json(res, 200, {
        ok: true,
        config: cfg,
        server: { ok: state.serverOk, error: state.serverErr, port: cfg.端口 },
        counts: { says: state.says, frames: state.frames },
        lastReply: state.lastReply,
      })
    })

    route('POST', '/dsh-fishbuddy/api/config', async (req, res) => {
      const body = await readBody(req)
      const next = readConfig()
      for (const k of ['会话', '回调', '挂件路径']) {
        if (typeof body[k] === 'string') next[k] = body[k].trim()
      }
      if (Number(body.端口) > 0) next.端口 = Number(body.端口)
      writeConfig(next)
      json(res, 200, { ok: true, config: next })
    })

    route('GET', '/dsh-fishbuddy/api/sessions', async (req, res) => {
      const controller = ctx.get('sessionController') || ctx.sessionController
      const out = []
      try {
        const list = controller?.list?.() ?? []
        for (const s of list) out.push({ id: s.id ?? s.sessionId, title: s.title ?? '' })
      } catch {
        /* ignore */
      }
      json(res, 200, { ok: true, sessions: out })
    })

    // 打开挂件设置（挂件在 8778 上开了 /settings）
    route('POST', '/dsh-fishbuddy/api/open-widget-settings', async (req, res) => {
      const cfg = readConfig()
      const base = String(cfg.回调 || '').replace(/\/hands\/reply.*$/, '')
      const url = (base || 'http://127.0.0.1:8778') + '/settings'
      try {
        const r = await fetch(url, { method: 'POST' })
        const body = await r.text()
        json(res, 200, { ok: r.ok, 说: body.slice(0, 200) })
      } catch (e) {
        json(res, 200, { ok: false, 说: '挂件没在跑：' + String(e?.message ?? e) })
      }
    })

    route('POST', '/dsh-fishbuddy/api/show-widget', async (req, res) => {
      const cfg = readConfig()
      const base = String(cfg.回调 || '').replace(/\/hands\/reply.*$/, '')
      try {
        const r = await fetch((base || 'http://127.0.0.1:8778') + '/show', { method: 'POST' })
        json(res, 200, { ok: r.ok })
      } catch (e) {
        json(res, 200, { ok: false, 说: String(e?.message ?? e) })
      }
    })

    // 启动挂件（open -a），给第一次用的人省一步
    route('POST', '/dsh-fishbuddy/api/launch', async (req, res) => {
      const cfg = readConfig()
      const app = String(cfg.挂件路径 || '')
      if (!app || !fs.existsSync(app)) {
        return json(res, 200, { ok: false, 说: '找不到挂件：在设置里填 .app 的路径' })
      }
      execFile('open', ['-a', app], (err) => {
        if (err) return json(res, 200, { ok: false, 说: String(err.message) })
        json(res, 200, { ok: true, 说: '挂件起来了' })
      })
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
