// ==UserScript==
// @name         BuonDua/misskon/nicesss/4kup → PhotoBook 助手
// @namespace    photobook.bridge
// @version      1.8.1
// @description  在 buondua.com / misskon.com / nicesss.com / 4kup.net 卡片右下角与详情页标题行右侧显示「下载/已入库」状态,点击推送到 PhotoBook 任务队列(同一本写真跨站转载也判已入库)
// @author       PhotoBook
// @match        https://buondua.com/*
// @match        https://www.buondua.com/*
// @match        https://misskon.com/*
// @match        https://www.misskon.com/*
// @match        https://www.nicesss.com/*
// @match        https://nicesss.com/*
// @match        https://4kup.net/*
// @match        https://www.4kup.net/*
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
      // misskon 老帖整页 URL 解析走服务端回源, 冷缓存时即使服务端已
      // 并发也可能超过 15s —— 放宽到 30s(解析结果服务端有缓存, 只慢一次)
      timeout: 30000,
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

  // 服务端 push 拒绝(false)时回的是 state;LABEL 里没有的(如 rejected =
  // URL 解析不出序号)以前会原样把英文状态画到徽标上(用户看到 "rejected")。
  const LABEL = {
    new: "⬇ 下载", queued: "⏳ 队列中", done: "✓ 已入库",
    failed: "✕ 失败·重推", skipped: "⊘ 跳过·重推", rejected: "✕ 链接无效",
  };
  const CLS = { new: "", queued: "is-busy", done: "is-done", failed: "is-off", skipped: "is-skip" };

  // ---- 卡片发现 ---------------------------------------------------------------
  // buondua 列表页卡片: div.items-row[data-id="<serial>"],封面容器 .item-thumb
  // misskon 列表页卡片: article.item-list(无 id, 序号取自详情链接 /<serial>-…/),
  //                     封面容器 .post-thumbnail
  // nicesss 列表页卡片: article.post[id="post-<id>"],封面容器 .entry-media
  //                     (卡片序号 = 详情 URL 的 <id>.html,与 post id 一致)
  // 4kup 列表页卡片:    article.generate-columns[id="post-<id>"](GP 主题),
  //                     封面容器 .post-thumbnail;序号 = post id,与详情页一致
  // 详情页: URL 尾段 serial,封面容器 .post-image / 标题行(.entry-title, nicesss)
  const IS_NICESSS = /(^|\.)nicesss\.com$/.test(location.hostname);
  const IS_MISSKON = /(^|\.)misskon\.com$/.test(location.hostname);
  const IS_4KUP = /(^|\.)4kup\.net$/.test(location.hostname);

  function cardNodes() {
    if (IS_NICESSS) {
      return Array.from(document.querySelectorAll("article.post[id^='post-']"));
    }
    if (IS_MISSKON) {
      return Array.from(document.querySelectorAll("article.item-list"));
    }
    if (IS_4KUP) {
      return Array.from(document.querySelectorAll("article[id^='post-']"));
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
    // 4kup slug 同样无序号(/le-gms-006a-gms/),与 misskon 老帖同思路
    // 回退 body class 的 postid-N(GP 主题详情页都有)
    if (IS_4KUP) {
      return (document.body.className.match(/postid-(\d+)/) || [])[1] || null;
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
    if (IS_4KUP) {
      // 详情页有 h1.entry-title(GP 主题列表页卡片是 h2,页头无 entry-title)
      return Boolean(document.querySelector("h1.entry-title"));
    }
    return Boolean(document.querySelector(".article-tags, .post-image"));
  }

  function ensureHost(card) {
    const sel = IS_NICESSS ? ".entry-media"
      : IS_MISSKON ? ".post-thumbnail" : IS_4KUP ? ".post-thumbnail" : ".item-thumb";
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
    if (IS_4KUP) {
      // 卡片 id 就是 post id(与详情页一致),链接 slug 无序号
      const m = card.id.match(/^post-(\d+)$/);
      if (m) return m[1];
      const a = card.querySelector("a[href*='://4kup.net/']");
      return a ? "" : "";
    }
    return card.dataset.id;
  }

  // 卡片标题文本(随状态查询上报服务端做跨站标题比对,判「已入库」)
  function cardTitle(card) {
    const sel = IS_NICESSS ? "h2.entry-title a"
      : IS_MISSKON ? "h2.post-box-title a" : IS_4KUP ? "h2.entry-title a" : ".page-header h2 a.item-link";
    const a = card.querySelector(sel);
    return a ? (a.textContent || "").trim() : "";
  }

  // 详情页标题: og:title 最干净(无分页尾巴的在 JSON-LD 里),退回 h1
  function detailTitle() {
    const m = document.querySelector('meta[property="og:title"]');
    let t = m ? (m.content || "").trim() : "";
    if (t) {
      // 去掉 buondua 分页尾巴 " ( Page 1 / 2 )"
      t = t.replace(/\s*\(\s*Page\s+\d+\s*\/\s*\d+\s*\)\s*$/i, "");
      // 去掉 4kup og:title 的站点后缀(h1 无;服务端入库标题也不带)
      t = t.replace(/\s*[–—-]\s*Beautiful Girls Collection\s*$/i, "");
      return t;
    }
    const h = document.querySelector("h1");
    return h ? (h.textContent || "").trim() : "";
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
    if (IS_4KUP) {
      // 标题 h1.entry-title 行,徽标内联挂标题右侧(站内没有 tag 行,
      // 分类在 footer 的 .cat-links 里且只有地区/出品方分类,不适合挂)
      const title = document.querySelector("h1.entry-title");
      if (title) {
        title.style.display = "flex";
        title.style.flexWrap = "wrap";
        title.style.alignItems = "center";
        title.style.gap = "8px";
        return title;
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
    const text = pending === "pending" ? "…" : (LABEL[st] || "✕ 推送失败");
    // 标签行内联布局(标记类含 tags / post-tag / entry-title), 非封面绝对定位
    const inline = /(^|\s)(tags|post-tag|entry-title)(\s|$)/.test(host.className);
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
      (pending === "pending" ? "is-wait" : (st in CLS ? CLS[st] : "is-off"));
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

    // 无序号可查(整页都是老帖): 直接走 URL 解析通道。
    // 混合页(部分卡片有 slug 序号、部分是老帖)两条通道都要走: 老帖的
    // unknown 在纯序号分支里不能丢(tag/搜索页实测 1.7.1 只查到 1 张)。
    if (unknown.length) {
      resolveUnknown(unknown, cards);
    }
    if (!serials.size) return;
    // 状态查询带页面标题: 服务端对「状态 new 且标题与已入库写真等价」的
    // 序号当场登记进 source_serials 并返回 done —— 跨站转载序号独立,
    // 服务端只有在用户浏览到该站页面时才能第一次见到那个序号。
    const dsTitle = ds ? detailTitle() : "";
    const items = Array.from(serials).map(serial => ({
      serial: Number(serial),
      title: ds === serial ? dsTitle : cardTitle(
        cards.find(c => String(cardSerial(c)) === String(serial)) || {}),
    }));
    api("POST", "/api/ext/status", { items }, function (ok, data) {
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
  // 请求带 titles(url → 页面标题): 状态 new 且标题与已入库写真等价时,
  // 服务端登记序号并返回 done —— 老帖列表页卡片取不到序号, 这是唯一登记通道。
  // 服务端返回的 serial 持久化到 GM 存储: 后续轮询(甚至下次访问)该 URL
  // 直接并入按序号的 /status 通道, 不再每 5s 重复走服务端解析+回源取页面。
  function resolvedSerial(url) {
    return GM_getValue("pb_serial:" + url, null);
  }

  function rememberSerial(url, serial) {
    try { GM_setValue("pb_serial:" + url, String(serial)); } catch (_) {}
  }

  function resolveUnknown(urls, cards) {
    // 已解析过的 URL 直接并入按序号的主通道; 只把全新的交给 URL 通道
    const known = urls.filter(u => resolvedSerial(u));
    const fresh = urls.filter(u => !resolvedSerial(u));
    if (!fresh.length) {
      if (known.length) queryBySerial(known.map(u => ({
        url: u, serial: resolvedSerial(u),
        title: u === location.href ? detailTitle() : cardTitle(
          cards.find(c => {
            const a = c.querySelector("a[href*='://misskon.com/']");
            return a && a.href === u;
          }) || {})}), cards));
      return;
    }
    const titles = {};
    fresh.forEach(u => {
      if (u === location.href) {
        titles[u] = detailTitle();
        return;
      }
      const card = cards.find(c => {
        const a = c.querySelector("a[href*='://misskon.com/']");
        return a && a.href === u;
      });
      if (card) titles[u] = cardTitle(card);
    });
    api("POST", "/api/ext/status-by-url",
      { urls: fresh, titles: titles },
      function (ok, data) {
        if (!ok || !data || !data.items) return;
        const byUrl = {};
        data.items.forEach(i => {
          byUrl[i.url] = i;
          if (i.serial != null) rememberSerial(i.url, i.serial);
        });
        applyUnknown(byUrl, cards);
      });
  }

  // 已知序号的 URL → 并入主状态查询(带标题, 顺带维持跨站登记通道)
  function queryBySerial(entries, cards) {
    const items = entries.map(e => ({ serial: Number(e.serial), title: e.title || "" }));
    api("POST", "/api/ext/status", { items }, function (ok, data) {
      if (!ok || !data || !data.items) return;
      const byUrl = {};
      data.items.forEach((i, k) => {
        if (entries[k]) byUrl[entries[k].url] = { url: entries[k].url, serial: i.serial, state: i.state };
      });
      applyUnknown(byUrl, cards);
    });
  }

  function applyUnknown(byUrl, cards) {
    cards.forEach(c => {
      const a = c.querySelector("a[href*='://misskon.com/']");
      if (!a) return;
      const item = byUrl[a.href];
      const host = ensureHost(c);
      if (!host) return;
      // state 为空 = resolveUnknown 对「本次没查状态、只补序号」的 known URL 的兜底项:
      // 不能重画(会把已有徽标抹成空白), 跳过等下一轮主通道/查询回调来画
      if (item && item.state == null) return;
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
      if (item && item.state == null) return;
      if (!item || item.serial == null) {
        setBadge(host, "", item && item.state ? item.state : "new", null);
      } else {
        setBadge(host, String(item.serial), item.state,
          pending.has(String(item.serial)) ? "pending" : null);
      }
    }
  }

  // ---- 点击推送 ----------------------------------------------------------------
  function onClick(el, host, serial) {
    if (!pingOk) { alert("PhotoBook 未连接,请在脚本菜单重新设置"); return; }
    const state = el.dataset.state;
    if (state === "done" || state === "queued" || el.dataset.busy) return;
    // 列表页卡片自带详情链接(a.item-link / misskon、4kup 的详情链接 /
    // nicesss 的 a[href*='.html']); 详情页的徽标挂在本页自己身上, 直接推
    // 当前 URL —— 不能再从宿主节点里找链接: misskon 详情页的徽标挂在
    // p.post-tag(标签行)上, 行里全是 https://misskon.com/tag/... 归档链接,
    // 抓到的是标签页, 服务端解析不出序号 → state=rejected(2026-10-24
    // FEILIN Video No.031 就是这么"下载按钮点击后显示 rejected"的)。
    const linkSel = IS_NICESSS ? "a[href*='.html']"
      : IS_MISSKON ? "a[href*='://misskon.com/']"
      : IS_4KUP ? "a[href*='://4kup.net/']" : "a.item-link";
    const link = isDetailPage() ? null : host.querySelector(linkSel);
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
  let queryTimer = null;   // 未声明会在严格模式下每轮抛 ReferenceError, 中断轮询链

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
