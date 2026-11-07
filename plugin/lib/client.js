/**
 * dsh-fishbuddy-mac —— 客户端半边：DSH「设置 → 大肥鱼」
 *
 * 只做四件事：
 *   1. 选会话（送到哪一间）
 *   2. 启动挂件 / 打开挂件设置 / 让挂件露头
 *   3. 保存配置（每次保存整份，未显示的字段不会被抹掉）
 *   4. 显示插件与挂件的连通状态
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
      wrap: { maxWidth: 720, color: "var(--dsw-alias-label-primary)", fontSize: 13 },
      title: { fontSize: 16, fontWeight: 500, margin: "0 0 6px" },
      intro: { color: "var(--dsw-alias-label-tertiary)", margin: "0 0 12px", lineHeight: "20px" },
      row: {
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
        padding: "10px 0",
        borderBottom: ".5px solid var(--dsw-alias-border-l2)",
        flexWrap: "wrap",
      },
      label: { minWidth: 120, fontWeight: 500 },
      hint: { color: "var(--dsw-alias-label-tertiary)", fontSize: 11.5, lineHeight: "17px", marginTop: 3 },
      input: {
        background: "transparent",
        border: "1px solid var(--dsw-alias-border-l2)",
        borderRadius: 6,
        color: "var(--dsw-alias-label-primary)",
        fontSize: 12.5,
        height: 28,
        padding: "0 8px",
        minWidth: 320,
        outline: "none",
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
      out: {
        whiteSpace: "pre-wrap",
        background: "rgba(127,127,127,.08)",
        borderRadius: 8,
        padding: "10px 12px",
        marginTop: 10,
        color: "var(--dsw-alias-label-secondary)",
        fontFamily: "ui-monospace,SFMono-Regular,Menlo,monospace",
        fontSize: 11.5,
      },
      err: { color: "var(--dsw-alias-state-error-primary)", marginTop: 8, whiteSpace: "pre-line" },
    };

    async function call(path, opts) {
      const r = await fetch(API + path, {
        headers: { "content-type": "application/json" },
        ...opts,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.ok === false) throw new Error(j.error || j["说"] || "HTTP " + r.status);
      return j;
    }

    function FishBuddySection() {
      const [cfg, setCfg] = useState(null);
      const [sessions, setSessions] = useState([]);
      const [state, setState] = useState(null);
      const [msg, setMsg] = useState("");
      const [busy, setBusy] = useState("");

      const load = useCallback(async () => {
        try {
          const [s, ss] = await Promise.all([call("/state"), call("/sessions")]);
          setCfg(s.config);
          setState(s);
          setSessions(ss.sessions || []);
          setMsg("");
        } catch (e) {
          setMsg(String(e.message || e));
        }
      }, []);

      useEffect(() => {
        void load();
      }, [load]);

      const save = async () => {
        setBusy("save");
        try {
          await call("/config", { method: "POST", body: JSON.stringify(cfg) });
          setMsg("✓ 存好了");
          await load();
        } catch (e) {
          setMsg(String(e.message || e));
        } finally {
          setBusy("");
        }
      };

      const act = async (name, path, okText) => {
        setBusy(name);
        try {
          const r = await call(path, { method: "POST" });
          setMsg("✓ " + (r["说"] || okText));
        } catch (e) {
          setMsg(String(e.message || e));
        } finally {
          setBusy("");
        }
      };

      if (!cfg) {
        return h("div", { style: S.wrap }, h("p", { style: S.intro }, msg || "读取配置中…"));
      }

      const port = cfg.端口 || 8777;
      const live = state?.server?.ok;

      return h(
        "div",
        { style: S.wrap },
        h("h2", { style: S.title }, "大肥鱼"),
        h(
          "p",
          { style: S.intro },
          "桌面挂件 ⇄ 这间会话的接线。挂件负责听、看、说；真正回你话的是你选的那一间会话。",
        ),

        h(
          "div",
          { style: S.row },
          h("div", { style: S.label }, "状态"),
          h(
            "div",
            null,
            h(
              "div",
              null,
              live ? `✓ 挂件口子 ${port} 在听` : `✗ 挂件口子没起来${state?.server?.error ? "：" + state.server.error : ""}`,
            ),
            h(
              "div",
              { style: S.hint },
              `说过 ${state?.counts?.says ?? 0} 次 · 收图 ${state?.counts?.frames ?? 0} 张` +
                (state?.lastReply ? ` · 最近回话：${String(state.lastReply).slice(0, 30)}` : ""),
            ),
          ),
        ),

        h(
          "div",
          { style: S.row },
          h("div", { style: S.label }, "送到哪一间"),
          h(
            "div",
            null,
            h(
              "select",
              {
                style: { ...S.input, minWidth: 380 },
                value: cfg["会话"] || "",
                onChange: (e) => setCfg({ ...cfg, 会话: e.target.value }),
              },
              h("option", { value: "" }, "（还没选）"),
              ...sessions.map((s) => h("option", { key: s.id, value: s.id }, `${s.title || "(无标题)"} · ${s.id}`)),
            ),
            h("div", { style: S.hint }, "挂件说的话会当作你在这间会话里说的；她的最后一轮回话会推回挂件气泡。"),
          ),
        ),

        h(
          "div",
          { style: S.row },
          h("div", { style: S.label }, "挂件路径"),
          h(
            "div",
            null,
            h("input", {
              style: { ...S.input, minWidth: 460 },
              value: cfg["挂件路径"] || "",
              placeholder: "/Applications/DSH-FishBuddy.app",
              onChange: (e) => setCfg({ ...cfg, 挂件路径: e.target.value }),
            }),
            h("div", { style: S.hint }, "「启动挂件」用它；填 .app 的完整路径。"),
          ),
        ),

        h(
          "div",
          { style: S.row },
          h("div", { style: S.label }, "回话递回"),
          h(
            "div",
            null,
            h("input", {
              style: S.input,
              value: cfg["回调"] || "",
              onChange: (e) => setCfg({ ...cfg, 回调: e.target.value }),
            }),
            h("div", { style: S.hint }, "默认 http://127.0.0.1:8778/hands/reply —— 挂件监听的那个口。"),
          ),
        ),

        h(
          "div",
          { style: { display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14, paddingTop: 12, borderTop: ".5px solid var(--dsw-alias-border-l2)" } },
          h("button", { style: S.btn, onClick: save, disabled: !!busy }, busy === "save" ? "保存中…" : "保存"),
          h("button", { style: S.btn2, onClick: () => act("launch", "/launch", "挂件起来了"), disabled: !!busy }, busy === "launch" ? "启动中…" : "启动挂件"),
          h("button", { style: S.btn2, onClick: () => act("settings", "/open-widget-settings", "设置打开了"), disabled: !!busy }, "打开挂件设置"),
          h("button", { style: S.btn2, onClick: () => act("show", "/show-widget", "挂件出来了"), disabled: !!busy }, "让挂件露头"),
          h("button", { style: S.btn2, onClick: load, disabled: !!busy }, "刷新"),
        ),

        msg ? h("div", { style: msg.startsWith("✓") ? { ...S.out } : S.err }, msg) : null,
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
