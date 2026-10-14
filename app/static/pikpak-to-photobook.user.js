// ==UserScript==
// @name         PikPak to PhotoBook
// @namespace    photobook.bridge
// @version      1.2.3
// @description  在 mypikpak.com 勾选文件/文件夹,一键推送到 PhotoBook 任务队列下载入库。勾选的文件夹就是写真集(里面是写真图片),标签第一个作为模特名。修复原脚本分享页文件夹下载 100 条限制。
// @author       PhotoBook
// @match        https://mypikpak.com/*
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
  // 原脚本用 localStorage 存 aria2 四项;这里换成 PhotoBook 地址 + API Key,
  // 与 PhotoBook 助手脚本(buondua-bridge.user.js)同一套约定。
  const CFG_KEY = { base: "pb_base", key: "pb_key", tags: "pb_pikpak_tags" };
  let BASE = (GM_getValue(CFG_KEY.base, "") || "").replace(/\/+$/, "");
  let KEY = GM_getValue(CFG_KEY.key, "") || "";
  // 标签记忆: 第一个标签就是模特名(后端 model_name 取 tags[0])
  let TAGS = GM_getValue(CFG_KEY.tags, "") || "";

  GM_registerMenuCommand("设置 PhotoBook", promptSettings);
  GM_registerMenuCommand("刷新选中项", function () { snapshotSelection(); Dialog.open(); });

  if (!BASE || !KEY) {
    showOff("PhotoBook 未配置,点此设置");
  }

  function promptSettings() {
    const b = prompt("PhotoBook 地址(如 http://192.168.0.100:8777)", BASE);
    if (b === null) return;
    const k = prompt("API Key(管理后台 → 设置 → 浏览器联动)", KEY);
    if (k === null) return;
    BASE = b.trim().replace(/\/+$/, "");
    KEY = k.trim();
    GM_setValue(CFG_KEY.base, BASE);
    GM_setValue(CFG_KEY.key, KEY);
    hideOff();
    ping();
  }

  // ---- 右下角徽标(未配置/未连接时显示) -------------------------------------
  function showOff(text) {
    let el = document.getElementById("pb-off");
    if (!el) {
      el = document.createElement("div");
      el.id = "pb-off";
      el.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:99999;" +
        "padding:8px 14px;border-radius:20px;background:rgba(176,66,48,.92);" +
        "color:#fff;font-size:13px;font-weight:600;cursor:pointer;" +
        "box-shadow:0 2px 8px rgba(0,0,0,.3)";
      el.addEventListener("click", function () { promptSettings(); });
      (document.body || document.documentElement).appendChild(el);
    }
    el.style.display = "block";
    el.textContent = "📷 " + text;
  }

  function hideOff() {
    const el = document.getElementById("pb-off");
    if (el) el.style.display = "none";
  }

  // ---- HTTP(GM 跨域) -------------------------------------------------------
  function api(method, path, body, cb) {
    if (!BASE) { showOff("PhotoBook 地址未配置"); cb(false, null, 0); return; }
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
        if (r.status === 401) { showOff("API Key 无效,点此重设"); }
        cb(r.status >= 200 && r.status < 300, data, r.status);
      },
      onerror: function () { cb(false, null, 0); },
      ontimeout: function () { cb(false, null, 0); },
    });
  }

  function ping() {
    api("GET", "/api/ext/ping", null, function (ok, data) {
      if (ok) { console.info("[PB] connected, server", data && data.version); hideOff(); }
      else showOff("PhotoBook 未连接,点此重试");
    });
  }
  if (BASE && KEY) ping();

  // ---- PikPak API ----------------------------------------------------------
  // 与原脚本同一套取 token 的方式(页面 localStorage 里的 credentials / captcha)。
  function isSharePage() { return location.pathname.startsWith("/S/") || location.pathname.startsWith("/s/"); }
  function getShareId() { return location.pathname.split("/")[2]; }
  // 深层分享页 URL 带层级: /s/<shareId>/<目录ID>/…, 最后一段是当前打开的目录。
  // 之前固定取根目录("") → 深层页面勾选的文件和根列表对不上号, 全部「未匹配」。
  // URL 最后一段是当前目录 ID(原版脚本从 fetch 拦截拿, 这里从 URL 解析, 等价)。
  function getShareParentId() {
    const seg = location.pathname.split("/").filter(Boolean);
    return seg.length > 2 ? seg[seg.length - 1] : "";
  }
  function isPluginPage() { return isSharePage() || location.pathname.startsWith("/drive"); }

  function getSharePageData() {
    const state = getPiniaState();
    return (state && state.share) || null;
  }

  // Pinia 状态: 优先 Nuxt, 失败再走 #app.__vue_app__(两个入口 PikPak 不同页面表现不一)
  function getPiniaState() {
    try {
      const nuxt = unsafeWindow.useNuxtApp();
      if (nuxt && nuxt.$pinia && nuxt.$pinia.state) return nuxt.$pinia.state.value;
    } catch (e) {}
    try {
      const pinia = document.getElementById("app").__vue_app__
        .config.globalProperties.$pinia;
      return pinia.state.value;
    } catch (e) {}
    return null;
  }

  function getSelectedIds() {
    const state = getPiniaState();
    if (!state) return [];
    const ids = (state.share && state.share.selectedIds)
      || (state.file && state.file.selectedIds) || [];
    if (ids.length) return ids;
    // 兜底: PikPak 改版会把选中状态挪进别的 store — 扫全部 store 找 selectedIds
    for (const k in state) {
      const v = state[k];
      if (v && Array.isArray(v.selectedIds) && v.selectedIds.length) return v.selectedIds;
    }
    return [];
  }

  function getHeader() {
    let token = "", captcha = "", clientId = "";
    const storage = window.localStorage;
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (!key) continue;
      if (key.startsWith("credentials")) {
        const d = JSON.parse(storage.getItem(key) || "{}");
        token = d.token_type + " " + d.access_token;
      } else if (key.startsWith("captcha")) {
        const d = JSON.parse(storage.getItem(key) || "{}");
        captcha = d.captcha_token;
        const m = key.match(/captcha_(.+)/);
        clientId = (m && m[1]) || "";
      }
    }
    const deviceId = storage.getItem("deviceid") || "";
    const parts = deviceId.split(".");
    const xDeviceId = parts.length >= 2
      ? `${parts[0]}.${parts[parts.length - 1].substring(0, 32)}` : deviceId;
    const headers = {
      Authorization: token,
      "x-device-id": xDeviceId,
      "x-client-id": clientId,
      "x-captcha-token": captcha,
    };
    if (isSharePage()) headers.Referer = location.href;
    return headers;
  }

  function req(url, opts) {
    opts = opts || {};
    return new Promise(function (resolve, reject) {
      GM_xmlhttpRequest({
        method: opts.method || "GET",
        url: url,
        headers: opts.headers || {},
        data: opts.data || null,
        responseType: opts.responseType || "json",
        timeout: 60000,
        onload: function (res) {
          if (opts.responseType === "blob") return resolve(res);
          if (res.response || res.responseText) resolve(res.response || res.responseText);
          else reject(new Error("empty response"));
        },
        onerror: function () { reject(new Error("network error")); },
        ontimeout: function () { reject(new Error("timeout")); },
      });
    });
  }

  // 原脚本 getList: limit=500 且不分页 —— 只拿第一页, 超过 500 就漏。
  // 这里统一走分页游标 next_page_token, 见 fetchFolderAll。
  function apiFiles(parentId) {
    return req("https://api-drive.mypikpak.com/drive/v1/files"
      + "?thumbnail_size=SIZE_MEDIUM&limit=100&parent_id=" + encodeURIComponent(parentId)
      + "&with_audit=true&filters=%7B%22phase%22%3A%7B%22eq%22%3A%22PHASE_TYPE_COMPLETE%22%7D%2C%22trashed%22%3A%7B%22eq%22%3Afalse%7D%7D",
      { headers: getHeader() });
  }

  function apiEvents() {
    return req("https://api-drive.mypikpak.com/drive/v1/events?thumbnail_size=SIZE_MEDIUM&limit=100",
      { headers: getHeader() });
  }

  function getList(parentId) {
    if (parentId === "recent") {
      return apiEvents().then(function (r) {
        return { files: (r.events || []).map(function (e) { return e.reference_resource; }).filter(Boolean) };
      });
    }
    return apiFiles(parentId);
  }

  // ---- 分享页 --------------------------------------------------------------
  // 原脚本的 100 条限制就出在这里: fetchShareFiles 只请求一次 share/detail,
  // limit=100 写死, 既不翻页也不校验 next_page_token。分享页文件夹超过 100
  // 个文件时, 后面的文件全部静默丢失。fetchFolderAll 用 page_token 循环取全。
  const PAGE_SIZE = 100;   // share/detail 单页上限(服务端硬顶)

  function fetchShareFiles(shareId, parentId, passCodeToken) {
    let url = "https://api-drive.mypikpak.com/drive/v1/share/detail?share_id="
      + encodeURIComponent(shareId) + "&limit=" + PAGE_SIZE
      + "&thumbnail_size=SIZE_LARGE&folders_first=true";
    if (parentId) url += "&parent_id=" + encodeURIComponent(parentId);
    if (passCodeToken) url += "&pass_code_token=" + encodeURIComponent(passCodeToken);
    return req(url, { headers: getHeader() });
  }

  // 翻页取全一个目录(不受 100 条限制)。返回 {files, truncated}
  function fetchFolderAll(shareId, parentId, passCodeToken, onProgress) {
    let files = [];
    let pageToken = "";
    let guard = 0;
    return (function loop() {
      let url = "https://api-drive.mypikpak.com/drive/v1/share/detail?share_id="
        + encodeURIComponent(shareId) + "&limit=" + PAGE_SIZE
        + "&thumbnail_size=SIZE_LARGE&folders_first=true";
      if (parentId) url += "&parent_id=" + encodeURIComponent(parentId);
      if (passCodeToken) url += "&pass_code_token=" + encodeURIComponent(passCodeToken);
      if (pageToken) url += "&page_token=" + encodeURIComponent(pageToken);
      return req(url, { headers: getHeader() }).then(function (res) {
        const batch = (res && res.files) || [];
        files = files.concat(batch);
        if (onProgress) onProgress(files.length);
        pageToken = res && res.next_page_token || "";
        // 防御: 服务端偶发回环(page_token 不变), 连翻 50 页(5000 文件)后收手
        if (pageToken && ++guard < 50) return loop();
        return files;
      });
    })();
  }

  // 递归展开文件夹 → 该文件夹下的文件列表(不含文件夹自身)。
  // 每项带 rel(相对文件夹根的路径), 推送时按它落盘, 子目录结构能保留。
  function expandShareTree(shareId, folderId, passCodeToken, out, seen, prefix) {
    return fetchFolderAll(shareId, folderId, passCodeToken).then(function (children) {
      const subs = [];
      for (const f of children) {
        if (!f || !f.id || seen[f.id]) continue;
        seen[f.id] = true;
        const rel = prefix ? prefix + "/" + f.name : f.name;
        if (f.kind === "drive#folder") { subs.push(f); }
        else out.push({ id: f.id, name: f.name, size: f.size, rel: rel });
      }
      // 逐个递归子文件夹: 不能用 return 提前结束, 否则同层后续条目被丢弃
      return subs.reduce(function (p, s) {
        return p.then(function () {
          return expandShareTree(shareId, s.id, passCodeToken, out, seen,
                                prefix ? prefix + "/" + s.name : s.name);
        });
      }, Promise.resolve()).then(function () { return out; });
    });
  }

  // 取单个文件的下载直链(分享页走 share/file_info)
  function getShareFileLink(shareId, fileId, passCodeToken) {
    const url = "https://api-drive.mypikpak.com/drive/v1/share/file_info?share_id="
      + encodeURIComponent(shareId) + "&file_id=" + encodeURIComponent(fileId)
      + "&pass_code_token=" + encodeURIComponent(passCodeToken);
    return req(url, { headers: getHeader() }).then(function (res) {
      const fi = res.file_info;
      if (!fi) throw new Error("file_info 为空");
      if (!fi.web_content_link && fi.medias && fi.medias.length) {
        fi.web_content_link = fi.medias[0].link.url;
      }
      if (!fi.web_content_link) throw new Error("web_content_link 为空");
      return fi;
    });
  }

  // 按 ID 直查条目信息(不依赖当前目录列表)。
  // 分享页 share/file_info 对文件和文件夹都返回; drive 页 files/{id} 同理。
  // 文件夹会带 keywords/audit 等元数据; 判断文件夹用 kind, 没有就按有无
  // web_content_link 兜底(文件夹没有直链)。
  function getEntryInfo(fileId) {
    if (isSharePage()) {
      const data = getSharePageData();
      const token = (data && data.data && data.data.pass_code_token) || "";
      const url = "https://api-drive.mypikpak.com/drive/v1/share/file_info?share_id="
        + encodeURIComponent(getShareId()) + "&file_id=" + encodeURIComponent(fileId)
        + "&pass_code_token=" + encodeURIComponent(token);
      return req(url, { headers: getHeader() }).then(function (res) {
        const fi = res.file_info || res;
        if (!fi || (!fi.name && !fi.id)) throw new Error("file_info 为空");
        return fi;
      });
    }
    return req("https://api-drive.mypikpak.com/drive/v1/files/" + fileId + "?",
      { headers: getHeader() }).then(function (res) {
        if (!res || !res.name) throw new Error("file detail 为空");
        return res;
      });
  }

  function getDriveFileLink(fileId) {
    return req("https://api-drive.mypikpak.com/drive/v1/files/" + fileId + "?",
      { headers: getHeader() }).then(function (res) {
        if (!res.web_content_link && res.medias && res.medias.length) {
          res.web_content_link = res.medias[0].link.url;
        }
        if (!res.web_content_link) throw new Error("web_content_link 为空");
        return res;
      });
  }

  function getDownloadLink(fileId) {
    if (isSharePage()) {
      const data = getSharePageData();
      const token = (data && data.data && data.data.pass_code_token) || "";
      return getShareFileLink(getShareId(), fileId, token);
    }
    return getDriveFileLink(fileId);
  }

  // ---- 样式 ----------------------------------------------------------------
  const CSS = `
  .pb-pk-btn{position:fixed;z-index:9999;width:50px;height:50px;border:0;padding:0;
    border-radius:50%;cursor:pointer;background:linear-gradient(135deg,#4f46e5,#8b5cf6);
    color:#fff;box-shadow:0 4px 12px rgba(79,70,229,.35);display:flex;align-items:center;
    justify-content:center;transition:transform .2s,box-shadow .2s}
  .pb-pk-btn:hover{transform:scale(1.06);box-shadow:0 6px 16px rgba(79,70,229,.45)}
  .pb-pk-btn svg{width:24px;height:24px}
  .pb-pk-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:3000}
  .pb-pk-dialog{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);
    z-index:10000;width:min(720px,92vw);max-height:88vh;display:flex;flex-direction:column;
    background:#fff;border-radius:16px;box-shadow:0 24px 60px rgba(0,0,0,.25);overflow:hidden;
    font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;color:#1e293b}
  .pb-pk-dialog *{box-sizing:border-box}
  .pb-pk-head{display:flex;align-items:center;justify-content:space-between;
    padding:18px 24px;border-bottom:1px solid #e2e8f0}
  .pb-pk-title{margin:0;font-size:17px;font-weight:700}
  .pb-pk-close{width:32px;height:32px;border:0;border-radius:8px;background:#f1f5f9;
    color:#64748b;font-size:18px;cursor:pointer}
  .pb-pk-close:hover{background:#e2e8f0;color:#334155}
  .pb-pk-body{padding:20px 24px;overflow-y:auto;flex:1}
  .pb-pk-field{margin-bottom:16px}
  .pb-pk-label{display:block;font-weight:600;margin-bottom:6px;font-size:13px;color:#334155}
  .pb-pk-hint{font-size:12px;color:#94a3b8;margin-top:5px;line-height:1.5}
  .pb-pk-input{width:100%;padding:9px 12px;border:1px solid #cbd5e1;border-radius:8px;
    font-size:14px;font-family:inherit;transition:border-color .15s}
  .pb-pk-input:focus{outline:0;border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.12)}
  .pb-pk-conn{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:12px 16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;margin-bottom:18px}
  .pb-pk-status{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:500;color:#475569}
  .pb-pk-dot{width:9px;height:9px;border-radius:50%;background:#94a3b8;flex:none}
  .pb-pk-dot.ok{background:#10b981}
  .pb-pk-dot.bad{background:#ef4444}
  .pb-pk-dot.testing{background:#f59e0b}
  .pb-pk-test{padding:6px 14px;font-size:13px;border:1px solid #cbd5e1;border-radius:8px;
    background:#fff;color:#475569;cursor:pointer;white-space:nowrap}
  .pb-pk-test:hover{border-color:#6366f1;color:#4f46e5}
  .pb-pk-test:disabled{opacity:.6;cursor:default}
  .pb-pk-summary{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
  .pb-pk-badge{display:inline-flex;align-items:center;padding:4px 12px;border-radius:20px;
    font-size:12px;font-weight:600}
  .pb-pk-badge.folder{background:rgba(251,191,36,.15);color:#b45309;border:1px solid rgba(251,191,36,.35)}
  .pb-pk-badge.file{background:rgba(99,102,241,.1);color:#4f46e5;border:1px solid rgba(99,102,241,.25)}
  .pb-pk-size{font-size:13px;color:#64748b}
  .pb-pk-list{list-style:none;margin:0 0 4px;padding:0;max-height:260px;overflow-y:auto;
    border:1px solid #eef2f6;border-radius:10px}
  .pb-pk-item{display:flex;align-items:center;gap:10px;padding:9px 14px;font-size:13px;
    border-bottom:1px solid #f1f5f9}
  .pb-pk-item:last-child{border-bottom:0}
  .pb-pk-item.is-folder{background:rgba(251,191,36,.04)}
  .pb-pk-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .pb-pk-bytes{color:#64748b;font-size:12px;white-space:nowrap}
  .pb-pk-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:16px 24px;border-top:1px solid #e2e8f0;background:#fafbfc}
  .pb-pk-btn2{padding:10px 20px;border:0;border-radius:9px;font-size:14px;font-weight:600;
    cursor:pointer;transition:filter .15s}
  .pb-pk-btn2:hover{filter:brightness(1.06)}
  .pb-pk-btn2.primary{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff}
  .pb-pk-btn2.ghost{background:#fff;color:#475569;border:1px solid #cbd5e1}
  .pb-pk-btn2:disabled{opacity:.55;cursor:default}
  .pb-pk-toast{position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:10001;
    padding:10px 18px;border-radius:10px;color:#fff;font-size:13px;font-weight:500;
    box-shadow:0 4px 14px rgba(0,0,0,.18);max-width:80vw}
  .pb-pk-toast.ok{background:rgba(16,185,129,.94)}
  .pb-pk-toast.bad{background:rgba(239,68,68,.94)}
  .pb-pk-toast.info{background:rgba(79,70,229,.94)}
  .pb-pk-progress{height:8px;background:#e2e8f0;border-radius:8px;overflow:hidden;margin:10px 0 6px}
  .pb-pk-bar{height:100%;background:linear-gradient(90deg,#4f46e5,#8b5cf6);width:0;
    transition:width .25s}
  .pb-pk-empty{padding:36px 20px;text-align:center;color:#94a3b8;font-size:13px}
  .pb-pk-spin{display:inline-block;width:14px;height:14px;border:2px solid #cbd5e1;
    border-top-color:#4f46e5;border-radius:50%;animation:pbspin .7s linear infinite;vertical-align:-2px}
  @keyframes pbspin{to{transform:rotate(360deg)}}
  `;
  const style = document.createElement("style");
  style.textContent = CSS;
  document.head.appendChild(style);

  // ---- 小工具 --------------------------------------------------------------
  const $ = function (html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstChild;
  };

  function fmtBytes(n) {
    n = n || 0;
    if (!n) return "";
    const u = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(n) / Math.log(1024));
    return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + u[i];
  }

  function toast(msg, kind) {
    document.querySelectorAll(".pb-pk-toast").forEach(function (n) { n.remove(); });
    const el = $(`<div class="pb-pk-toast ${kind || "info"}"></div>`);
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, kind === "bad" ? 6000 : 3200);
  }

  // ---- 弹窗 ----------------------------------------------------------------
  const Dialog = {
    el: null,

    open: function () {
      if (this.el) { this.el.remove(); }
      this.build();
      this.bind();
      this.loadSelection();
      document.body.appendChild(this.el);
    },

    close: function () {
      if (this.el) { this.el.remove(); this.el = null; }
    },

    build: function () {
      const self = this;
      this.el = $(`
        <div>
          <div class="pb-pk-overlay" data-close></div>
          <div class="pb-pk-dialog" role="dialog" aria-modal="true">
            <div class="pb-pk-head">
              <h2 class="pb-pk-title">推送到 PhotoBook</h2>
              <button class="pb-pk-close" data-close title="关闭">×</button>
            </div>
            <div class="pb-pk-body">
              <div class="pb-pk-conn">
                <div class="pb-pk-status">
                  <span class="pb-pk-dot testing"></span>
                  <span class="pb-pk-conn-text">正在连接…</span>
                </div>
                <button class="pb-pk-test" data-action="test">测试连接</button>
              </div>

              <div class="pb-pk-field">
                <label class="pb-pk-label" for="pb-pk-tags">标签</label>
                <input class="pb-pk-input" id="pb-pk-tags" type="text"
                       placeholder="模特,Cosplay">
                <p class="pb-pk-hint">逗号分隔。<b>第一个标签就是模特名</b>(入库按它建立/复用模特,留空归入「未分类」),其余标签用于前台分类筛选。</p>
              </div>

              <div data-body></div>
            </div>
            <div class="pb-pk-foot">
              <button class="pb-pk-btn2 ghost" data-action="config">配置 PhotoBook</button>
              <button class="pb-pk-btn2 primary" data-action="push" disabled>推送到队列</button>
            </div>
          </div>
        </div>`);

      this.$ = function (sel) { return self.el.querySelector(sel); };
      this.$all = function (sel) { return Array.from(self.el.querySelectorAll(sel)); };

      // 记住上次的标签
      this.$("#pb-pk-tags").value = TAGS || "模特";
      this.items = [];
      this.selected = [];
      this.totalSize = 0;
      this.busy = false;
      // 弹窗内任何鼠标/键盘事件都不冒泡到页面(PikPak 会当成页面交互,
      // 点空白清勾选、按键触发快捷键)
      const self2 = this;
      ["mousedown", "pointerdown", "mouseup", "pointerup", "click",
       "keydown", "keyup", "keypress"].forEach(function (ev) {
        self2.el.addEventListener(ev, function (e) { e.stopPropagation(); });
      });
    },

    bind: function () {
      const self = this;
      this.$all("[data-close]").forEach(function (n) {
        n.addEventListener("click", function () { self.close(); });
      });
      this.$("[data-action=config]").addEventListener("click", function () { promptSettings(); });
      this.$("[data-action=test]").addEventListener("click", function () { self.testConn(); });
      this.$("[data-action=push]").addEventListener("click", function () { self.push(); });
      // 输入框里的键盘事件别漏到页面: PikPak 全局快捷键(如 a 全选/ESC 清空)
      // 会把勾选改掉, 导致填标签时勾选状态"自己"掉
      this.$all("input").forEach(function (inp) {
        ["keydown", "keyup", "keypress"].forEach(function (ev) {
          inp.addEventListener(ev, function (e) { e.stopPropagation(); });
        });
      });
      // Esc 关闭(捕获阶段先于页面快捷键, 且阻止到达 PikPak 的清空监听)
      this._esc = function (e) {
        if (e.key === "Escape") { e.stopPropagation(); self.close(); }
      };
      document.addEventListener("keydown", this._esc, true);
    },
    setConn: function (state, text) {
      const dot = this.$(".pb-pk-dot");
      dot.className = "pb-pk-dot " + (state === "ok" ? "ok" : state === "bad" ? "bad" : "testing");
      this.$(".pb-pk-conn-text").textContent = text;
    },

    testConn: function () {
      const self = this;
      const btn = this.$("[data-action=test]");
      btn.disabled = true;
      this.setConn("testing", "正在测试…");
      api("GET", "/api/ext/ping", null, function (ok, data) {
        btn.disabled = false;
        if (ok) self.setConn("ok", "已连接 · 服务端 v" + (data && data.version || "?"));
        else self.setConn("bad", "连接失败 — 检查地址与 API Key");
      });
    },

    setBody: function (html) { this.$("[data-body]").innerHTML = html; },

    // 读取勾选项 → 匹配文件信息 → 展开文件夹
    loadSelection: function () {
      const self = this;
      let ids = getSelectedIds();
      if (!ids.length && Date.now() - LAST_SEL.at < 15000) {
        // 点浮动按钮的瞬间可能已被页面清空勾选 → 用最近一次选中快照兜底
        ids = LAST_SEL.ids;
      }
      if (!ids.length) {
        this.setBody('<div class="pb-pk-empty">未选择文件<br>请在 PikPak 页面上勾选文件或文件夹后重试</div>');
        this.$("[data-action=push]").disabled = true;
        this.testConn();
        return;
      }
      this.testConn();
      this.setBody('<div class="pb-pk-empty"><span class="pb-pk-spin"></span> 正在读取选中项（含文件夹展开）…</div>');

      const share = isSharePage();
      const data = share ? getSharePageData() : null;
      const passCodeToken = (share && data && data.data && data.data.pass_code_token) || "";
      const shareId = share ? getShareId() : "";

      Promise.resolve()
        .then(function () { return self.matchSelected(ids, share, shareId, passCodeToken, data); })
        .then(function (r) { self.renderSelection(r); })
        .catch(function (e) {
          console.warn("[PB] loadSelection failed", e);
          self.setBody('<div class="pb-pk-empty">选中项读取失败:' + (e && e.message || e)
            + '<br>刷新页面后重试</div>');
        });
    },

    matchSelected: function (ids, share, shareId, passCodeToken, pageData) {
      const self = this;
      const out = { files: [], folders: [], unmatched: [] };
      // 当前目录文件(分页取全, 不受 100 条限制); 失败不致命 — 后面还有按 ID 直查
      let curPromise;
      if (share) {
        curPromise = fetchFolderAll(shareId, getShareParentId(), passCodeToken).then(function (f) {
          return f;
        }).catch(function (e) {
          console.warn("[PB] fetch current dir failed, will query by id", e);
          return [];
        });
      } else {
        const parentId = window.location.href.split("/").pop();
        curPromise = getList(parentId === "all" ? "" : parentId)
          .then(function (r) { return (r && r.files) || []; })
          .catch(function () { return []; });
      }

      return curPromise.then(function (curFiles) {
        const byId = {};
        curFiles.forEach(function (f) { if (f.id) byId[f.id] = f; });

        // 勾选项 = 当前页文件 + 当前页文件夹(含 Pinia 兜底, 原脚本同款)
        const items = [];
        ids.forEach(function (id) {
          const f = byId[id];
          if (f) {
            if (f.kind === "drive#folder") out.folders.push(f);
            else out.files.push(f);
          } else {
            out.unmatched.push(id);
          }
        });

        if (!out.folders.length) {
          // 分享页 Pinia 兜底: 接口没返回时用页面数据里的文件补齐
          if (share && pageData && pageData.curDirFiles) {
            const pf = Array.isArray(pageData.curDirFiles) ? pageData.curDirFiles
              : (pageData.curDirFiles.files || []);
            const map = {};
            pf.forEach(function (f) { map[f.id] = f; });
            out.unmatched = out.unmatched.filter(function (id) {
              const f = map[id];
              if (!f) return true;
              if (f.kind === "drive#folder") out.folders.push(f); else out.files.push(f);
              return false;
            });
          }
        }

        // 未匹配的 ID 逐个直查(列表对不上号的场景: 深层目录/改版/缓存滞后)。
        // 文件夹 → 递归展开成写真集; 文件 → 自成一个勾项。全部失败才放弃。
        const toResolve = out.unmatched.slice();
        out.unmatched = [];
        return toResolve.reduce(function (p, id) {
          return p.then(function () {
            return getEntryInfo(id).then(function (fi) {
              if (fi.kind === "drive#folder") {
                out.folders.push(fi);
              } else {
                out.files.push(fi);
              }
            }).catch(function (e) {
              console.warn("[PB] resolve by id failed", id, e);
              out.unmatched.push(id);
            });
          });
        }, Promise.resolve()).then(function () {
          if (!out.folders.length) {
            // 勾的全是单个文件: 每个文件自成一个勾项(files 就是自己)
            return { folders: [], files: out.files, unmatched: out.unmatched };
          }

          // 逐个文件夹展开成它自己的 files[](一个勾选项一个写真集)。
          // 单个文件夹展开失败不拖垮整批: 记空列表照常出按钮, 推送时该项被跳过。
          let expandFail = 0;
          const seen = new Set();
          out.folders.forEach(function (f) { seen[f.id] = true; });
          return out.folders.reduce(function (p, folder) {
            return p.then(function () {
              const acc = [];
              const expand = share
                ? expandShareTree(shareId, folder.id, passCodeToken, acc, seen)
                : expandDriveTree(folder, acc, seen);
              return expand.then(function () { folder._files = acc; })
                .catch(function (e) {
                  console.warn("[PB] expand folder failed", folder.name, e);
                  expandFail++;
                  folder._files = [];
                });
            });
          }, Promise.resolve()).then(function () {
            return { folders: out.folders, files: out.files,
                     unmatched: out.unmatched, expandFail: expandFail };
          });
        });
      });
    },

    renderSelection: function (r) {
      this.folders = r.folders;
      // 单个文件自成一个勾选项(files = 自己); 文件夹已由 matchSelected
      // 展开好 _files
      (r.files || []).forEach(function (f) {
        if (!f._files) f._files = [{ id: f.id, name: f.name, size: f.size, rel: f.name }];
      });
      this.items = r.folders.concat(r.files);   // 勾选项(文件夹在前, 与页面一致)
      this.totalSize = this.items.reduce(function (s, f) {
        return s + (parseInt(f.size) || 0);
      }, 0);

      let html = "";
      if (r.folders.length || r.files.length) {
        html += '<div class="pb-pk-summary">';
        if (r.folders.length) html += `<span class="pb-pk-badge folder">${r.folders.length} 个写真集(文件夹)</span>`;
        if (r.files.length) html += `<span class="pb-pk-badge file">${r.files.length} 个文件</span>`;
        if (r.unmatched.length) html += `<span class="pb-pk-badge file">${r.unmatched.length} 个未匹配</span>`;
        if (r.expandFail) html += `<span class="pb-pk-badge file">${r.expandFail} 个文件夹展开失败(将被跳过)</span>`;
        if (this.totalSize) html += `<span class="pb-pk-size">预估 ${fmtBytes(this.totalSize)}</span>`;
        html += "</div>";
        html += '<ul class="pb-pk-list">';
        this.items.slice(0, 200).forEach(function (f) {
          const isDir = f.kind === "drive#folder";
          html += `<li class="pb-pk-item${isDir ? " is-folder" : ""}"><span>${isDir ? "📁" : "📄"}</span><span class="pb-pk-name">${esc(f.name)}</span>` +
            (f.size ? `<span class="pb-pk-bytes">${fmtBytes(parseInt(f.size))}</span>` : "") + "</li>";
        });
        if (this.items.length > 200) html += `<li class="pb-pk-item"><span></span><span class="pb-pk-name">… 其余 ${this.items.length - 200} 项一并推送</span></li>`;
        html += "</ul>";
        if (this.items.length > 50) {
          html += `<p class="pb-pk-hint" style="margin:8px 0 0">勾选项较多,推送会在后台逐个进行,可在 PhotoBook 后台查看进度。</p>`;
        }
      } else {
        html = r.unmatched.length
          ? `<div class="pb-pk-empty">${r.unmatched.length} 个勾选项读取失败<br>可能是需要输入提取码或登录已过期<br>刷新 PikPak 页面、重新勾选后重试</div>`
          : '<div class="pb-pk-empty">未选择文件<br>请先在页面上勾选要下载的写真集(文件或文件夹),再点击本按钮</div>';
      }
      this.setBody(html);
      this.$("[data-action=push]").disabled = !this.items.length;
    },

    // ---- 推送 --------------------------------------------------------------
    // 逐个勾选项解析其中每个文件的直链(PikPak 直链带时效, 推送前解析;
    // 并发 8 平衡速度与限流)。一个勾选项 = 一个 item, files 按相对路径排列。
    resolveLinks: function (items, onProg) {
      const CONC = 8;
      let i = 0, ok = 0, fail = 0;
      const total = items.reduce(function (n, it) { return n + it._files.length; }, 0);

      function worker() {
        if (i >= items.length) return Promise.resolve();
        const item = items[i++];
        if (!item._files.length) return worker();
        const out = [];
        let j = 0;
        return (function next() {
          if (j >= item._files.length) {
            if (out.length) {
              ok++;
              item.files = out;
            } else {
              fail++;
            }
            return null;
          }
          const f = item._files[j++];
          return getDownloadLink(f.id).then(function (info) {
            out.push({
              file_id: f.id,
              name: f.name || "pikpak",
              url: info.web_content_link,
              rel: f.rel || f.name || f.id,
              size: parseInt(f.size) || parseInt(info.size) || 0,
            });
          }).catch(function (e) {
            console.warn("[PB] link failed", f && f.name, e);
          }).then(next);
        })().then(function () {
          if (onProg) onProg(ok + fail, total);
          return worker();
        });
      }

      const ws = [];
      for (let k = 0; k < CONC; k++) ws.push(worker());
      return Promise.all(ws).then(function () {
        return { items: items.filter(function (it) { return it.files && it.files.length; }),
                 ok: ok, fail: fail };
      });
    },

    push: function () {
      const self = this;
      if (this.busy) return;
      if (!BASE || !KEY) {
        toast("请先配置 PhotoBook 地址与 API Key", "bad");
        promptSettings();
        return;
      }
      if (!this.items.length) return;

      // 记住标签(下次打开自动带出); 模特名 = 第一个标签, 由后端取 tags[0]
      TAGS = this.$("#pb-pk-tags").value.trim();
      GM_setValue(CFG_KEY.tags, TAGS);

      const tags = TAGS.split(/[,，]/).map(function (s) { return s.trim(); })
        .filter(Boolean);
      const model = tags.length ? tags[0] : "";

      this.busy = true;
      const btn = this.$("[data-action=push]");
      btn.disabled = true;
      btn.textContent = "解析直链…";
      const totalFiles = this.items.reduce(function (n, it) {
        return n + it._files.length;
      }, 0);
      this.setBody(
        '<div class="pb-pk-empty">' +
        '<div style="margin-bottom:10px">正在解析直链 <b data-link-prog>0</b> / ' + totalFiles + "</div>" +
        '<div class="pb-pk-progress"><div class="pb-pk-bar" data-bar></div></div>' +
        '<p class="pb-pk-hint" style="margin:0">直链由 PikPak 下发,文件多时需要一点时间。</p></div>');

      this.resolveLinks(this.items, function (done, n) {
        const el = self.$("[data-link-prog]");
        const bar = self.$("[data-bar]");
        if (el) el.textContent = done;
        if (bar) bar.style.width = (n ? Math.round(done / n * 100) : 0) + "%";
      }).then(function (r) {
        if (!r.items.length) {
          self.busy = false;
          btn.textContent = "推送到队列";
          btn.disabled = false;
          self.setBody('<div class="pb-pk-empty">直链解析全部失败(' + r.fail + " 个勾选项)<br>请刷新 PikPak 页面后重试</div>");
          toast("直链解析失败", "bad");
          return;
        }
        btn.textContent = "推送中…";
        return self.send(r, tags, model, btn);
      });
    },

    send: function (r, tags, model, btn) {
      const self = this;
      // 超过后端上限时按批切(FastAPI 单请求体上限 5000; 一个勾选项的
      // files 可能上千, 所以按「文件数」而不是「勾选项数」切批)
      const CHUNK = 2000;
      const chunks = [];
      let cur = { items: [], n: 0 };
      r.items.forEach(function (it) {
        cur.items.push(it);
        cur.n += it.files.length;
        if (cur.n >= CHUNK) { chunks.push(cur); cur = { items: [], n: 0 }; }
      });
      if (cur.items.length) chunks.push(cur);

      let queued = 0, skipped = 0, failed = false;
      let k = 0;

      function next() {
        if (k >= chunks.length) {
          self.busy = false;
          btn.disabled = false;
          btn.textContent = "推送到队列";
          if (!queued) {
            self.setBody('<div class="pb-pk-empty">没有新任务入队(' + skipped + " 个已在队列)<br>这些写真集可能已在下载或已入库</div>");
            toast("没有新任务 — 均已在队列中", "info");
            return;
          }
          const msg = `已推送 ${queued} 个写真集到队列` + (skipped ? `，跳过 ${skipped} 个已入队` : "")
            + (r.fail ? `，${r.fail} 个直链解析失败` : "");
          self.setBody('<div class="pb-pk-empty">' + msg + "<br>可在 PhotoBook 后台「任务队列」查看下载进度</div>");
          toast(msg, r.fail && !queued ? "bad" : "ok");
          return;
        }
        const chunk = chunks[k++];
        api("POST", "/api/ext/pikpak", {
          items: chunk.items.map(function (it) {
            return { file_id: it.id, name: it.name || "pikpak", files: it.files };
          }),
          model_name: model, tags: tags,
        }, function (ok, data) {
          if (ok && data) {
            queued += data.queued || 0;
            skipped += data.skipped || 0;
          } else {
            failed = true;
            toast("推送失败（HTTP 或鉴权错误）", "bad");
          }
          next();
        });
      }
      next();
    },
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---- 驱动页目录树(非分享页) ----------------------------------------------
  // 原脚本 getList(parentId) 的 limit=500 同样只取首页; 这里补翻页。
  // 展开结果带 rel(相对 folder 根的路径); 文件夹本身只作为遍历节点, 不入列。
  function expandDriveTree(folder, out, seen, prefix) {
    function walk(parentId, pref) {
      let pageToken = "";
      let guard = 0;
      return (function loop() {
        let url = "https://api-drive.mypikpak.com/drive/v1/files?thumbnail_size=SIZE_MEDIUM"
          + "&limit=100&parent_id=" + encodeURIComponent(parentId)
          + "&with_audit=true&filters=%7B%22phase%22%3A%7B%22eq%22%3A%22PHASE_TYPE_COMPLETE%22%7D%2C%22trashed%22%3A%7B%22eq%22%3Afalse%7D%7D";
        if (pageToken) url += "&page_token=" + encodeURIComponent(pageToken);
        return req(url, { headers: getHeader() }).then(function (res) {
          const files = (res && res.files) || [];
          const subs = [];
          for (const f of files) {
            if (!f.id || seen[f.id]) continue;
            seen[f.id] = true;
            const rel = pref ? pref + "/" + f.name : f.name;
            if (f.kind === "drive#folder") { subs.push(f); }
            else out.push({ id: f.id, name: f.name, size: f.size, rel: rel });
          }
          pageToken = res && res.next_page_token || "";
          if (pageToken && ++guard < 50) return loop();
          return subs.reduce(function (p, s) {
            return p.then(function () {
              return walk(s.id, pref ? pref + "/" + s.name : s.name);
            });
          }, Promise.resolve());
        });
      })();
    }
    return walk(folder.id, prefix || "");
  }

  // ---- 选中快照 --------------------------------------------------------------
  // 点浮动按钮的瞬间 PikPak 可能把 document 级点击当成"取消选中", 勾选被清空,
  // 弹窗打开时 getSelectedIds() 已拿不到东西 → 平时持续快照, 出现这种时回退用快照。
  const LAST_SEL = { ids: [], at: 0 };

  function snapshotSelection() {
    const ids = getSelectedIds();
    if (ids.length) { LAST_SEL.ids = ids.slice(); LAST_SEL.at = Date.now(); }
  }

  // ---- 挂浮动按钮 ----------------------------------------------------------
  function mount() {
    if (document.getElementById("pb-pk-float")) return;
    if (!isPluginPage()) return;
    const btn = $(`<button class="pb-pk-btn" id="pb-pk-float" title="推送到 PhotoBook">
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
      </svg></button>`);
    btn.style.right = "24px";
    btn.style.top = "96px";
    // PikPak 在 mousedown 上清空勾选(原版脚本同款结论): 按钮上把
    // mousedown/pointerdown/click 全部拦下, 页面监听收不到事件就不会清。
    // 快照兜底仍保留, 防页面在捕获阶段监听的极端情况。
    ["pointerdown", "mousedown"].forEach(function (ev) {
      btn.addEventListener(ev, function (e) { e.stopPropagation(); });
    });
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      e.preventDefault();
      snapshotSelection();
      Dialog.open();
    });
    (document.body || document.documentElement).appendChild(btn);
  }

  document.cookie = "pp_access_to_visit=true";
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setTimeout(mount, 800); });
  } else {
    setTimeout(mount, 800);
  }
  // SPA 路由切换后按钮可能被移除, 兜底重挂; 同时持续快照勾选状态
  setInterval(mount, 5000);
  setInterval(function () {
    if (isPluginPage() && !Dialog.el) snapshotSelection();
  }, 1000);
  // mousedown/pointerdown 捕获阶段抢先快照: 页面清空勾选发生在 click,
  // 此时上一拍的选中项还在, 弹窗打开时勾选已没了也能用快照兜底
  ["pointerdown", "mousedown"].forEach(function (ev) {
    document.addEventListener(ev, function () {
      if (isPluginPage() && !Dialog.el) snapshotSelection();
    }, true);
  });
})();
