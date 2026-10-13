// ==UserScript==
// @name         BuonDua/misskon/nicesss → PhotoBook 助手
// @namespace    photobook.bridge
// @version      1.4.0
// @description  在 buondua.com / misskon.com / nicesss.com 卡片右下角与详情页标题行右侧显示「下载/已入库」状态,点击推送到 PhotoBook 任务队列(同一本写真跨站转载也判已入库)
// @author       PhotoBook
// @match        https://buondua.com/*
// @match        https://www.buondua.com/*
// @match        https://misskon.com/*
// @match        https://www.misskon.com/*
// @match        https://www.nicesss.com/*
// @match        https://nicesss.com/*
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
  .pb-badge{position:absolute;right:8px;bottom:8px;z-index:9999;min-width:26px;height:26px;
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
  .pb-badge--inline{position:static;margin-left:auto;flex:none;min-height:26px;height:auto;
    padding:4px 10px;border-radius:13px}
  .pb-badge--inline.is-done:hover{transform:none}
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
  // buondua 列表页卡片: div.items-row[data-id="<serial>"],封面容器 .item-thumb
  // misskon 列表页卡片: article.item-list(无 id, 序号取自详情链接 /<serial>-…/),
  //                     封面容器 .post-thumbnail
  // nicesss 列表页卡片: article.post[id="post-<id>"],封面容器 .entry-media
  //                     (卡片序号 = 详情 URL 的 <id>.html,与 post id 一致)
  // 详情页: URL 尾段 serial,封面容器 .post-image / 标题行(.entry-title, nicesss)
  const IS_NICESSS = /(^|\.)nicesss\.com$/.test(location.hostname);
  const IS_MISSKON = /(^|\.)misskon\.com$/.test(location.hostname);

  function cardNodes() {
    if (IS_NICESSS) {
      return Array.from(document.querySelectorAll("article.post[id^='post-']"));
    }
    if (IS_MISSKON) {
      return Array.from(document.querySelectorAll("article.item-list"));
    }
    return Array.from(document.querySelectorAll("div.items-row[data-id]"));
  }

  // misskon 详情 URL: /<serial>-<slug>/(分卷尾段 /2/ /3/ 无 serial,取前段)
  function misskonSerialFromPath(path) {
    const m = path.replace(/\/\d+\/?$/, "").match(/\/(\d{3,})(?:-|$)/);
    return m ? m[1] : null;
  }

  function serialFromLocation() {
    if (IS_NICESSS) {
      const m = location.pathname.match(/\/(\d+)\.html?$/);
      return m ? m[1] : null;
    }
    // 老帖 slug 无序号前缀(如 /xiuren-no-962-…/),回退 body class 的 postid-N
    if (IS_MISSKON) {
      return misskonSerialFromPath(location.pathname)
        || (document.body.className.match(/postid-(\d+)/) || [])[1] || null;
    }
    const m = location.pathname.match(/-(\d+)\/?$/);
    return m ? m[1] : null;
  }

  // 详情页判定: 必须真的有详情 DOM。tag 筛选页 URL 也可能以数字结尾
  // (buondua 是标签 id), 不能凭 URL 尾号当详情页, 否则会兜底抓到第一张卡片的
  // 封面并把它的徽标覆盖成标签 id 的状态。
  function isDetailPage() {
    if (IS_NICESSS) {
      return Boolean(document.querySelector(".article-content .entry-title"));
    }
    if (IS_MISSKON) {
      // 详情页有 h1.post-title + p.post-tag;列表页两者皆无
      return Boolean(document.querySelector("h1.post-title, p.post-tag"));
    }
    return Boolean(document.querySelector(".article-tags, .post-image"));
  }

  function ensureHost(card) {
    const sel = IS_NICESSS ? ".entry-media"
      : IS_MISSKON ? ".post-thumbnail" : ".item-thumb";
    const host = card.querySelector(sel);
    if (!host) return null;
    if (getComputedStyle(host).position === "static") {
      host.style.position = "relative";
    }
    return host;
  }

  function cardSerial(card) {
    if (IS_NICESSS) {
      // 卡片序号取详情链接尾段 id(post id 与之一致,链接更权威)
      const a = card.querySelector("a[href*='.html']");
      const m = a ? a.href.match(/\/(\d+)\.html?(?:[?#]|$)/) : null;
      if (m) return m[1];
      return card.id.replace(/^post-/, "");
    }
    if (IS_MISSKON) {
      const a = card.querySelector("a[href*='://misskon.com/']");
      // 老帖卡片链接也无序号,回退卡片自身(列表卡片在 body.postid-N 的详情页
      // 不成立,这里只能取链接;取不到就空,由服务端按 URL 解析)
      return a ? (misskonSerialFromPath(a.pathname) || "") : "";
    }
    return card.dataset.id;
  }

  function ensureDetailHost() {
    if (IS_NICESSS) {
      // 标题 h1 行(.entry-title),徽标内联挂标题右侧
      const title = document.querySelector(".article-content .entry-title");
      if (title) {
        title.style.display = "flex";
        title.style.flexWrap = "wrap";
        title.style.alignItems = "center";
        title.style.gap = "8px";
        return title;
      }
      return null;
    }
    if (IS_MISSKON) {
      // tag 行 p.post-tag,徽标内联挂行尾(与 buondua 的 .tags 行同款布局)
      const tagsRow = document.querySelector("p.post-tag");
      if (tagsRow) {
        tagsRow.style.display = "flex";
        tagsRow.style.flexWrap = "wrap";
        tagsRow.style.alignItems = "center";
        tagsRow.style.gap = "6px";
        return tagsRow;
      }
      return null;
    }
    // 首选: 标签行(.article-tags > .tags), 徽标挂行最右侧;
    // 找不到再退回封面容器(.post-image / .item-thumb)
    const tagsRow = document.querySelector(".article-tags .tags");
    if (tagsRow) {
      // 转成可换行的 flex 行, 徽标用 margin-left:auto 推到最右
      tagsRow.style.display = "flex";
      tagsRow.style.flexWrap = "wrap";
      tagsRow.style.alignItems = "center";
      return tagsRow;
    }
    const host = document.querySelector(".post-image") ||
                 document.querySelector(".item-thumb");
    if (!host) return null;
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    return host;
  }

  function setBadge(host, serial, state, pending) {
    const st = pending || state;
    const text = pending === "pending" ? "…" : (LABEL[st] || st);
    // 标签行内联布局(标记类含 tags / post-tag), 非封面绝对定位
    const inline = /(^|\s)(tags|post-tag)(\s|$)/.test(host.className);
    let el = host.querySelector(".pb-badge");
    if (!el) {
      el = document.createElement("button");
      el.className = "pb-badge" + (inline ? " pb-badge--inline" : "");
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
    el.className = "pb-badge " +
      (inline ? "pb-badge--inline " : "") +
      (pending === "pending" ? "is-wait" : CLS[st] || "");
    el.textContent = text;
    if (inline) el.style.marginLeft = "auto";
    // 已入库/队列中的按钮不响应点击
  }

  // ---- 状态查询 ---------------------------------------------------------------
  const pending = new Set();   // 本页刚点过、等待变"队列中"的 serial

  // 本地取不到序号的卡片/详情页(misskon 老帖 slug 无 <序号>- 前缀):
  // 徽标没有 serial 可查, 交给服务端按详情 URL 解析后再回填。
  // 收集本页所有这类详情 URL: 卡片链接 + 详情页自身。
  function unknownUrls() {
    const urls = new Set();
    if (IS_MISSKON) {
      cardNodes().forEach(c => {
        const a = c.querySelector("a[href*='://misskon.com/']");
        if (a && !misskonSerialFromPath(a.pathname)) urls.add(a.href);
      });
      if (isDetailPage() && !serialFromLocation()) urls.add(location.href);
    }
    return Array.from(urls);
  }

  function queryAndRender() {
    lastQuery = Date.now();
    const cards = cardNodes();
    const serials = new Set(cards.map(cardSerial));
    const ds = isDetailPage() ? serialFromLocation() : null;
    if (ds) serials.add(ds);
    serials.delete("");
    const unknown = unknownUrls();
    if (!serials.size && !unknown.length) return;

    // 无序号可查(整页都是老帖): 直接走 URL 解析通道
    if (!serials.size && unknown.length) {
      resolveUnknown(unknown, cards);
      return;
    }
    api("GET", "/api/ext/status?serials=" + Array.from(serials).join(","), null,
      function (ok, data) {
        if (!ok || !data || !data.items) return;
        const map = {};
        data.items.forEach(i => { map[i.serial] = i.state; });
        cards.forEach(c => {
          const host = ensureHost(c);
          const serial = cardSerial(c);
          if (host) setBadge(host, serial, map[serial] || "new",
            pending.has(serial) ? "pending" : null);
        });
        if (ds) {
          const host = ensureDetailHost();
          if (host) setBadge(host, ds, map[ds] || "new", pending.has(ds) ? "pending" : null);
        }
      });
  }

  // 老帖通道: POST /api/ext/status-by-url 让服务端按 URL 解析序号并判态。
  // 返回的 serial 同时回填徽标(后续轮询就能按序号查, 不再走这条通道)。
  function resolveUnknown(urls, cards) {
    api("POST", "/api/ext/status-by-url",
      { urls: urls },
      function (ok, data) {
        if (!ok || !data || !data.items) return;
        const byUrl = {};
        data.items.forEach(i => { byUrl[i.url] = i; });
        cards.forEach(c => {
          const a = c.querySelector("a[href*='://misskon.com/']");
          if (!a) return;
          const item = byUrl[a.href];
          const host = ensureHost(c);
          if (!host) return;
          if (!item || item.serial == null) {
            setBadge(host, "", item && item.state ? item.state : "new", null);
            return;
          }
          setBadge(host, String(item.serial), item.state,
            pending.has(String(item.serial)) ? "pending" : null);
        });
        if (isDetailPage() && !serialFromLocation()) {
          const item = byUrl[location.href];
          const host = ensureDetailHost();
          if (!host) return;
          if (!item || item.serial == null) {
            setBadge(host, "", item && item.state ? item.state : "new", null);
          } else {
            setBadge(host, String(item.serial), item.state,
              pending.has(String(item.serial)) ? "pending" : null);
          }
        }
      });
  }

  // ---- 点击推送 ----------------------------------------------------------------
  function onClick(el, host, serial) {
    if (!pingOk) { alert("PhotoBook 未连接,请在脚本菜单重新设置"); return; }
    const state = el.dataset.state;
    if (state === "done" || state === "queued" || el.dataset.busy) return;
    // 列表页卡片自带详情链接(a.item-link / misskon 的详情链接 / nicesss 的
    // a[href*='.html']); 详情页本身就是详情 URL, 直接用
    const linkSel = IS_NICESSS ? "a[href*='.html']"
      : IS_MISSKON ? "a[href*='://misskon.com/']" : "a.item-link";
    const link = host.querySelector(linkSel);
    const realUrl = link ? link.href : location.href;
    el.dataset.busy = "1";
    setBadge(host, serial, state, "pending");
    const force = (state === "failed" || state === "skipped");
    api("POST", "/api/ext/harvest", { url: realUrl, force },
      function (ok, data) {
        delete el.dataset.busy;
        const item = data && data.items && data.items[0];
        // 老帖卡片本地取不到序号 → 用服务端从 URL 解析出的序号刷新徽标
        if (item && item.serial) serial = item.serial;
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
  let lastQuery = 0;

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
    // 新卡片出现时尽快补一次查询。注意不能打断 loop 的保底轮询:
    // tag 等筛选页挂着广告 widget, DOM 变动持续不断(间隔 <600ms),
    // 旧版 clearTimeout+重启会把轮询无限饿死, 徽标一张都不出。
    // 这里独立计时 + 3s 节流: 变动触发提前查, 5s 轮询始终兜底。
    let moTimer = null;
    const mo = new MutationObserver(muts => {
      if (muts.some(badgeMutation)) return;
      if (moTimer) return;
      moTimer = setTimeout(function () {
        moTimer = null;
        if (Date.now() - lastQuery >= 3000) queryAndRender();
      }, 600);
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }
})();
