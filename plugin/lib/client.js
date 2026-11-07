/**
 * dsh-fishbuddy-mac —— 客户端半边：DSH「设置 → 大肥鱼」
 *
 * 分区：概览 / 会话 / 挂件 / 诊断 / 高级 / 最近事件
 * 数据都走同源的 /dsh-fishbuddy/api/*（DSH 自己的登录态 + 信任栅栏）。
 */
window.__ModuleLoader__.load({
  id: "dsh-fishbuddy-mac",
  factory: (require) => {
    const module = { exports: {} };
    const exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

    const React = require("react");
    const { createElement: h, useCallback, useEffect, useState } = React;

    const API = "/dsh-fishbuddy/api";

    const S = {
      wrap: { maxWidth: 780, color: "var(--dsw-alias-label-primary)", fontSize: 13 },
      title: { fontSize: 16, fontWeight: 600, margin: "0 0 6px" },
      intro: { color: "var(--dsw-alias-label-tertiary)", margin: "0 0 14px", lineHeight: "20px" },
      card: {
        border: ".5px solid var(--dsw-alias-border-l2)",
        borderRadius: 10,
        padding: "12px 14px",
        marginBottom: 12,
      },
      h3: { fontSize: 13, fontWeight: 600, margin: "0 0 8px" },
      row: { display: "flex", gap: 12, alignItems: "flex-start", padding: "7px 0", flexWrap: "wrap" },
      label: { minWidth: 104, color: "var(--dsw-alias-label-secondary)" },
      val: { flex: 1, minWidth: 220 },
      hint: { color: "var(--dsw-alias-label-tertiary)", fontSize: 11.5, lineHeight: "17px", marginTop: 3 },
      ok: { color: "var(--dsw-alias-state-success-primary, #2ea043)" },
      bad: { color: "var(--dsw-alias-state-error-primary)" },
      input: {
        background: "transparent",
        border: "1px solid var(--dsw-alias-border-l2)",
        borderRadius: 6,
        color: "var(--dsw-alias-label-primary)",
        fontSize: 12.5,
        height: 30,
        padding: "0 8px",
        outline: "none",
        width: "100%",
        boxSizing: "border-box",
      },
      btn: {
        background: "var(--dsw-alias-brand-primary)",
        color: "var(--dsw-alias-label-primary-foreground,#fff)",
        border: "none",
        borderRadius: 6,
        fontSize: 12.5,
        height: 30,
        padding: "0 12px",
        cursor: "pointer",
      },
      btn2: {
        background: "transparent",
        border: "1px solid var(--dsw-alias-border-l2)",
        color: "var(--dsw-alias-label-primary)",
        borderRadius: 6,
        fontSize: 12.5,
        height: 30,
        padding: "0 12px",
        cursor: "pointer",
      },
      mono: { fontFamily: "ui-monospace,SFMono-Regular,Menlo,monospace", fontSize: 11.5 },
      log: {
        maxHeight: 180,
        overflow: "auto",
        background: "rgba(127,127,127,.08)",
        borderRadius: 8,
        padding: "8px 10px",
        lineHeight: "18px",
      },
    };

    async function call(path, opts) {
      const r = await fetch(API + path, { headers: { "content-type": "application/json" }, ...opts });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || "HTTP " + r.status);
      if (j.ok === false) throw new Error(j["说"] || j.error || "失败");
      return j;
    }

    const when = (ms) => {
      if (!ms) return "—";
      const d = new Date(ms);
      const p = (n) => String(n).padStart(2, "0");
      return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    };

    function Row(props) {
      return h(
        "div",
        { style: S.row },
        h("div", { style: S.label }, props.label),
        h("div", { style: { ...S.val, ...(props.st || {}) } }, props.children),
      );
    }

    function Badge({ ok, text }) {
      return h("span", { style: ok ? S.ok : S.bad }, (ok ? "✓ " : "✗ ") + text);
    }

    function Section(props) {
      return h(
        "div",
        { style: { ...S.card, ...(props.style || {}) } },
        h("div", { style: S.h3 }, props.title),
        props.children,
      );
    }

    function FishBuddySection() {
      const [d, setD] = useState(null);
      const [sessions, setSessions] = useState([]);
      const [checks, setChecks] = useState(null);
      const [msg, setMsg] = useState("");
      const [busy, setBusy] = useState("");
      const [test, setTest] = useState("");

      const load = useCallback(async () => {
        try {
          const [st, ss] = await Promise.all([call("/state"), call("/sessions")]);
          setD(st);
          setSessions(ss.sessions || []);
          setMsg("");
        } catch (e) {
          setMsg(String(e.message || e));
        }
      }, []);

      useEffect(() => {
        void load();
      }, [load]);

      const run = async (name, fn, okText) => {
        setBusy(name);
        setMsg("");
        try {
          const r = await fn();
          if (okText !== false) setMsg("✓ " + (okText || r?.["说"] || "好了"));
          await load();
        } catch (e) {
          setMsg(String(e.message || e));
        } finally {
          setBusy("");
        }
      };

      if (!d) return h("div", { style: S.wrap }, h("p", { style: S.intro }, msg || "读取中…"));

      const cfg = d.config;
      const w = d.widget || {};
      const widgetLive = !!w.ok;
      const cur = sessions.find((s) => s.id === cfg["会话"]);

      const save = (patch) =>
        run("save" + Object.keys(patch).join(""), () =>
          call("/config", { method: "POST", body: JSON.stringify({ ...cfg, ...patch }) }),
        );

      return h(
        "div",
        { style: S.wrap },
        h("h2", { style: S.title }, "大肥鱼"),
        h(
          "p",
          { style: S.intro },
          "桌面挂件 ⇄ 会话的接线。挂件负责听、看、说；真正回你话的是你选的那间会话。",
        ),

        // ---------- 概览 ----------
        h(
          Section,
          { title: "概览" },
          h(Row, { label: "插件" }, h("span", null, `v${d.version}`), h("span", { style: { ...S.hint, marginLeft: 8 } }, `已运行 ${Math.round((d.uptimeSec || 0) / 60)} 分钟`)),
          h(Row, { label: "挂件口子" }, h(Badge, { ok: d.server?.ok, text: d.server?.ok ? `127.0.0.1:${d.server.port} 在听` : `没起来 ${d.server?.error || ""}` })),
          h(
            Row,
            { label: "挂件" },
            widgetLive
              ? h(Badge, { ok: true, text: `在线 · v${w.version || "?"} · ${w["形象"] === "minimal" ? "极简圆点" : "素材形象"} · 陪看${w.watching ? "开着" : "关着"}` })
              : h(Badge, { ok: false, text: `没应答（${w.error || "8778 不通"}）` }),
          ),
          h(Row, { label: "绑定会话" }, cur ? h("span", null, `${cur.title || "(无标题)"}`, h("span", { style: { ...S.hint, ...S.mono, marginLeft: 8 } }, cur.id)) : h("span", { style: S.bad }, cfg["会话"] ? cfg["会话"] + "（磁盘上没找到）" : "还没选")),
          h(Row, { label: "计数" }, h("span", { style: S.hint }, `说过 ${d.counts?.says ?? 0} 次 · 收图 ${d.counts?.frames ?? 0} 张`)),
          h(
            Row,
            { label: "最近回话" },
            d.lastReply
              ? h("div", null, h("div", null, d.lastReply), h("div", { style: S.hint }, when(d.lastReplyAt)))
              : h("span", { style: S.hint }, "还没有"),
          ),
        ),

        // ---------- 会话 ----------
        h(
          Section,
          { title: "送到哪一间会话" },
          h(
            "select",
            {
              style: S.input,
              value: cfg["会话"] || "",
              onChange: (e) => setD({ ...d, config: { ...cfg, 会话: e.target.value } }),
            },
            h("option", { value: "" }, "（还没选）"),
            ...sessions.map((s) =>
              h("option", { key: s.id, value: s.id }, `${s.title || "(无标题)"} · ${s.id.slice(0, 18)} · ${when(s.mtime)}`),
            ),
          ),
          h("div", { style: S.hint }, "挂件说的话会当作你在这间会话里说的；她的最后一轮回话会推回挂件气泡。"),
          h(
            "div",
            { style: { display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" } },
            h("button", { style: S.btn, onClick: () => save({ 会话: cfg["会话"] }), disabled: !!busy }, "保存"),
            h("button", { style: S.btn2, onClick: load, disabled: !!busy }, "刷新列表"),
            h("input", {
              style: { ...S.input, flex: 1, minWidth: 200, height: 30 },
              placeholder: "发一句测试…",
              value: test,
              onChange: (e) => setTest(e.target.value),
            }),
            h(
              "button",
              {
                style: S.btn2,
                disabled: !!busy || !test.trim(),
                onClick: () =>
                  run("say", async () => {
                    const r = await call("/say", { method: "POST", body: JSON.stringify({ text: test }) });
                    setTest("");
                    return r;
                  }, "发进去了"),
              },
              "发一句",
            ),
          ),
        ),

        // ---------- 挂件 ----------
        h(
          Section,
          { title: "挂件" },
          h(
            "div",
            { style: { display: "flex", gap: 8, flexWrap: "wrap" } },
            h("button", { style: S.btn, onClick: () => run("launch", () => call("/launch", { method: "POST" })), disabled: !!busy }, busy === "launch" ? "启动中…" : "启动挂件"),
            h("button", { style: S.btn2, onClick: () => run("settings", () => call("/open-widget-settings", { method: "POST" })), disabled: !!busy }, "打开挂件设置"),
            h("button", { style: S.btn2, onClick: () => run("show", () => call("/show-widget", { method: "POST" })), disabled: !!busy }, "露头"),
            h("button", { style: S.btn2, onClick: () => run("hide", () => call("/hide-widget", { method: "POST" })), disabled: !!busy }, "藏起来"),
          ),
          h("div", { style: { ...S.row, marginTop: 8 } },
            h("div", { style: S.label }, "App 路径"),
            h("input", {
              style: S.input,
              value: cfg["挂件路径"] || "",
              placeholder: "/Applications/DSH-FishBuddy.app",
              onChange: (e) => setD({ ...d, config: { ...cfg, 挂件路径: e.target.value } }),
            }),
          ),
          h("div", { style: { display: "flex", gap: 8, marginTop: 8 } },
            h("button", { style: S.btn2, onClick: () => save({ 挂件路径: cfg["挂件路径"] }), disabled: !!busy }, "保存路径"),
          ),
          h("div", { style: S.hint }, "「启动挂件」用这个路径；挂件里还有更细的设置（热键/形象/朗读/陪看间隔）。"),
        ),

        // ---------- 诊断 ----------
        h(
          Section,
          { title: "自检" },
          h(
            "div",
            { style: { display: "flex", gap: 8, alignItems: "center" } },
            h("button", { style: S.btn2, disabled: !!busy, onClick: () => run("doctor", async () => { const r = await call("/doctor", { method: "POST" }); setChecks(r.checks || []); return { "说": "检查完了" }; }) }, busy === "doctor" ? "检查中…" : "跑一遍"),
            checks ? h("span", { style: S.hint }, `${checks.filter((c) => c.ok).length}/${checks.length} 项通过`) : null,
          ),
          checks
            ? h(
                "div",
                { style: { marginTop: 8 } },
                ...checks.map((c, i) =>
                  h("div", { key: i, style: { ...S.row, padding: "4px 0" } },
                    h("div", { style: { width: 110, color: c.ok ? undefined : "var(--dsw-alias-state-error-primary)" } }, (c.ok ? "✓ " : "✗ ") + c.name),
                    h("div", { style: { ...S.hint, flex: 1, marginTop: 0 } }, c.detail || ""),
                  ),
                ),
              )
            : null,
        ),

        // ---------- 高级 ----------
        h(
          Section,
          { title: "高级" },
          h(Row, { label: "端口" },
            h("input", {
              style: { ...S.input, maxWidth: 140 },
              value: cfg["端口"] || 8777,
              onChange: (e) => setD({ ...d, config: { ...cfg, 端口: Number(e.target.value) || 8777 } }),
            }),
            h("span", { style: { ...S.hint, marginLeft: 8 } }, "改完要重启 DSH"),
          ),
          h(Row, { label: "回话递回" },
            h("input", {
              style: S.input,
              value: cfg["回调"] || "",
              onChange: (e) => setD({ ...d, config: { ...cfg, 回调: e.target.value } }),
            }),
          ),
          h("div", { style: S.hint }, "默认 http://127.0.0.1:8778/hands/reply —— 挂件监听的那个口。"),
          h("div", { style: { marginTop: 8 } },
            h("button", { style: S.btn, onClick: () => save({ 端口: cfg["端口"], 回调: cfg["回调"] }), disabled: !!busy }, "保存高级设置"),
          ),
        ),

        // ---------- 事件 ----------
        d.events?.length
          ? h(
              Section,
              { title: "最近发生的事" },
              h(
                "div",
                { style: { ...S.log, ...S.mono } },
                ...d.events.slice().reverse().map((e, i) =>
                  h("div", { key: i }, `${when(e.at)}  ${e.kind}  ${e.text}`),
                ),
              ),
            )
          : null,

        msg ? h("div", { style: msg.startsWith("✓") ? { ...S.hint, marginTop: 8 } : { ...S.bad, marginTop: 8 } }, msg) : null,
      );
    }

    const inject = ["slots"];
    const NS = "fishbuddy-mac";

    function apply(ctx) {
      ctx.effect(
        () =>
          ctx.slots.inject(
            "settings.section",
            () =>
              ctx.slots.register(
                { name: "settings.section", id: NS, order: 7, label: () => "大肥鱼" },
                FishBuddySection,
              ),
            "fishbuddy-mac: settings section",
          ),
        "fishbuddy-mac: settings section",
      );
    }

    exports.apply = apply;
    exports.inject = inject;
    exports.FishBuddySection = FishBuddySection;
    return module.exports;
  },
});
