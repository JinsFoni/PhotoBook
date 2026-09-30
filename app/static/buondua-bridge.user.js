// ==UserScript==
// @name         BuonDua → PhotoBook 助手
// @namespace    photobook.bridge
// @version      1.0.1
// @description  在 buondua.com 卡片右下角显示「下载/已入库」状态,点击推送到 PhotoBook 任务队列
// @author       PhotoBook
// @match        https://buondua.com/*
// @match        https://www.buondua.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  // ---- 配置(GM 存储) -------------------------------------------------------
  let BASE = (GM_getValue("pb_base", "") || "").replace(/\/+$/, "");
  let KEY = GM_getValue("pb_key", "") || "";

  GM_registerMenuCommand("设置 PhotoBook", promptSettings);

  GM_registerMenuCommand("刷新入库状态", function () { queryAndRender(); });

  if (!BASE || !KEY) {
    console.info("[PB] 未配置,菜单「设置 PhotoBook」或右下角红色徽标开始配置");
    showOff("PhotoBook 未配置,点此设置");
    return;
  }
  pingThenBoot(false);

  // ---- 可见状态徽标(未配置/未连接时显示, 避免静默失败) ----
  function showOff(text) {
    let el = document.getElementById("pb-off");
    if (!el) {
      el = document.createElement("div");
      el.id = "pb-off";
      el.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:99999;" +
        "padding:8px 14px;border-radius:20px;background:rgba(176,66,48,.92);" +
        "color:#fff;font-size:13px;font-weight:600;cursor:pointer;" +
        "box-shadow:0 2px 8px rgba(0,0,0,.3)";
      el.addEventListener("click", function () {
        el.textContent = "连接中…";
        promptSettings();
      });
      (document.body || document.documentElement).appendChild(el);
    }
    el.style.display = "block";
    el.textContent = "📷 " + text;
  }

  function hideOff() {
    const el = document.getElementById("pb-off");
    if (el) el.style.display = "none";
  }

  function promptSettings() {
    const b = prompt("PhotoBook 地址(如 http://192.168.0.100:8777)", BASE);
    if (b === null) return;
    const k = prompt("API Key(管理后台 → 设置 → 浏览器联动)", KEY);
    if (k === null) return;
    BASE = b.trim().replace(/\/+$/, "");
    KEY = k.trim();
    GM_setValue("pb_base", BASE);
    GM_setValue("pb_key", KEY);
    pingThenBoot(true);
  }

  // ---- 连通性 ---------------------------------------------------------------
  let pingOk = false;
  function pingThenBoot(notify) {
    api("GET", "/api/ext/ping", null, function (ok, data) {
      pingOk = ok;
      if (ok) {
        console.info("[PB] connected, server", data && data.version);
        hideOff();
        boot();
      } else {
        console.warn("[PB] ping 失败");
        showOff("未连接,点此检查设置/重试");
        if (notify) alert(
          "PhotoBook 连接失败。\n常见原因:\n" +
          "1. Tampermonkey 弹出的跨域授权提示未点「总是允许」\n" +
          "2. 地址或 API Key 不对\n" +
          "3. NAS 服务未启动");
      }
    });
  }

  // ---- HTTP(GM 跨域) --------------------------------------------------------
  function api(method, path, body, cb) {
    GM_xmlhttpRequest({
      method,
      url: BASE + path,
      headers: Object.assign({ "X-PhotoBook-Key": KEY },
        body ? { "Content-Type": "application/json" } : {}),
      data: body ? JSON.stringify(body) : null,
      timeout: 15000,
      onload: function (r) {
        let data = null;
        try { data = JSON.parse(r.responseText); } catch (_) {}
        if (r.status === 401) { pingOk = false; console.warn("[PB] Key 无效"); }
        cb(r.status >= 200 && r.status < 300, data, r.status);
      },
      onerror: function () { cb(false, null, 0); },
      ontimeout: function () { cb(false, null, 0); },
    });
  }

  // ---- 样式 -----------------------------------------------------------------
  const CSS = `
  .pb-badge{position:absolute;right:8px;bottom:8px;z-index:5;min-width:26px;height:26px;
    display:inline-flex;align-items:center;justify-content:center;gap:4px;padding:0 8px;
    border-radius:13px;border:0;cursor:pointer;font-size:12px;font-weight:600;
    color:#fff;background:rgba(20,20,24,.72);box-shadow:0 1px 4px rgba(0,0,0,.35);
    transition:background .15s,transform .15s;pointer-events:auto}
  .pb-badge:hover{background:rgba(20,20,24,.92);transform:translateY(-1px)}
  .pb-badge.is-done{cursor:default;background:rgba(34,139,84,.88)}
  .pb-badge.is-done:hover{transform:none;background:rgba(34,139,84,.88)}
  .pb-badge.is-busy{cursor:default;background:rgba(43,108,176,.88)}
  .pb-badge.is-off{cursor:pointer;background:rgba(176,66,48,.88)}
  .pb-badge.is-skip{cursor:pointer;background:rgba(90,90,96,.88)}
  .pb-badge.is-wait{cursor:wait;opacity:.7}
  .pb-shake{animation:pbshake .3s}
  @keyframes pbshake{25%{transform:translateX(-3px)}75%{transform:translateX(3px)}}
  `;
  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);

  const LABEL = {
    new: "⬇ 下载", queued: "⏳ 队列中", done: "✓ 已入库",
    failed: "✕ 失败·重推", skipped: "⊘ 跳过·重推",
  };
  const CLS = { new: "", queued: "is-busy", done: "is-done", failed: "is-off", skipped: "is-skip" };

  // ---- 卡片发现 ---------------------------------------------------------------
  // 列表页卡片: div.items-row[data-id="<serial>"],封面容器 .item-thumb(相对定位)
  // 详情页: URL 尾段 serial,封面容器 .post-image 或第一张 .item-thumb
  function cardNodes() {
    return Array.from(document.querySelectorAll("div.items-row[data-id]"));
  }

  function serialFromLocation() {
    const m = location.pathname.match(/-(\d+)\/?$/);
    return m ? m[1] : null;
  }

  function ensureHost(card) {
    // .item-thumb 需要 position:relative 才能挂绝对定位按钮
    const host = card.querySelector(".item-thumb");
    if (!host) return null;
    if (getComputedStyle(host).position === "static") {
      host.style.position = "relative";
    }
    return host;
  }

  function ensureDetailHost() {
    const host = document.querySelector(".post-image") ||
                 document.querySelector(".item-thumb");
    if (!host) return null;
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    return host;
  }

  function setBadge(host, serial, state, pending) {
    const st = pending || state;
    const text = pending === "pending" ? "…" : (LABEL[st] || st);
    let el = host.querySelector(".pb-badge");
    if (!el) {
      el = document.createElement("button");
      el.className = "pb-badge";
      el.type = "button";
      host.appendChild(el);
      el.addEventListener("click", function (ev) {
        ev.preventDefault(); ev.stopPropagation();
        onClick(el, host, serial);
      });
    } else if (el.dataset.state === st && el.textContent === text) {
      return;   // 无变化不写 DOM: 避免 MutationObserver 自反馈循环
    }
    el.dataset.state = st;
    el.dataset.serial = serial;
    el.className = "pb-badge " + (pending === "pending" ? "is-wait" : CLS[st] || "");
    el.textContent = text;
    // 已入库/队列中的按钮不响应点击
  }

  // ---- 状态查询 ---------------------------------------------------------------
  const pending = new Set();   // 本页刚点过、等待变"队列中"的 serial
  let queryTimer = null;

  function queryAndRender() {
    const cards = cardNodes();
    const serials = new Set(cards.map(c => c.dataset.id));
    const ds = serialFromLocation();
    if (ds) serials.add(ds);
    if (!serials.size) return;
    api("GET", "/api/ext/status?serials=" + Array.from(serials).join(","), null,
      function (ok, data) {
        if (!ok || !data || !data.items) return;
        const map = {};
        data.items.forEach(i => { map[i.serial] = i.state; });
        cards.forEach(c => {
          const host = ensureHost(c);
          if (host) setBadge(host, c.dataset.id, map[c.dataset.id] || "new",
            pending.has(c.dataset.id) ? "pending" : null);
        });
        if (ds) {
          const host = ensureDetailHost();
          if (host) setBadge(host, ds, map[ds] || "new", pending.has(ds) ? "pending" : null);
        }
      });
  }

  // ---- 点击推送 ----------------------------------------------------------------
  function onClick(el, host, serial) {
    if (!pingOk) { alert("PhotoBook 未连接,请在脚本菜单重新设置"); return; }
    const state = el.dataset.state;
    if (state === "done" || state === "queued" || el.dataset.busy) return;
    // 列表页卡片自带 a.item-link; 详情页本身就是详情 URL, 直接用
    const link = host.querySelector("a.item-link");
    const realUrl = link ? link.href : location.href;
    el.dataset.busy = "1";
    setBadge(host, serial, state, "pending");
    const force = (state === "failed" || state === "skipped");
    api("POST", "/api/ext/harvest", { url: realUrl, force },
      function (ok, data) {
        delete el.dataset.busy;
        const item = data && data.items && data.items[0];
        if (ok && item && item.ok) {
          pending.add(String(serial));
          setTimeout(() => { pending.delete(String(serial)); queryAndRender(); }, 1200);
          setBadge(host, serial, "queued");
          return;
        }
        // 失败: 抖动 + 恢复状态
        el.classList.add("pb-shake");
        setTimeout(() => el.classList.remove("pb-shake"), 350);
        const st = (item && item.state) || state;
        setBadge(host, serial, st === "duplicate" ? "done" : st);
        el.title = (item && item.message) || "推送失败";
      });
  }

  // ---- 启动 + 监听 --------------------------------------------------------------
  function loop() {
    queryAndRender();
    queryTimer = setTimeout(loop, 5000);
  }

  function badgeMutation(m) {
    // 只关心外部 DOM 变化: 本脚本写入的 .pb-badge 不再触发查询
    if (m.target.classList && m.target.classList.contains("pb-badge")) return true;
    if (m.addedNodes && Array.from(m.addedNodes).some(
        n => n.classList && n.classList.contains("pb-badge"))) return true;
    return false;
  }

  function boot() {
    loop();
    // 翻页/懒加载: 新卡片出现时立即查一次(节流: 打断循环,600ms 后重启)
    const mo = new MutationObserver(muts => {
      if (muts.some(badgeMutation)) return;
      clearTimeout(queryTimer);
      queryTimer = setTimeout(loop, 600);
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }
})();
