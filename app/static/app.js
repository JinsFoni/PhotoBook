/* ==========================================================================
   Photo Collection — shared runtime(SSR 适配版)
   Chrome (header / drawer / search / footer / lightbox) 由这里渲染;
   页面数据来自服务端注入的 window.PB_DATA / window.PB_BOOT。
   收藏为服务端存储(/api/favorites),主题偏好仍存 localStorage。
   ========================================================================== */

window.PC = (function () {
  var BOOT = window.PB_BOOT || { user: { name: "", role: "" }, path: "/" };
  var ME = BOOT.user || {};
  var I18N = BOOT.i18n || {};

  /* ---------- i18n ------------------------------------------------------- */
  function t(msg, vars) {
    var s = I18N[msg] !== undefined ? I18N[msg] : msg;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = s.split("{" + k + "}").join(String(vars[k]));
      });
    }
    return s;
  }

  /* ---------- icons ------------------------------------------------------ */
  var ICONS = {
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    heart: '<path d="M12 20.2s-7.4-4.5-7.4-9.6A4.3 4.3 0 0 1 12 7.9a4.3 4.3 0 0 1 7.4 2.7c0 5.1-7.4 9.6-7.4 9.6z"/>',
    download: '<path d="M12 4v11m0 0l-4-4m4 4l4-4M5 19h14"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    left: '<path d="M15 5l-7 7 7 7"/>',
    right: '<path d="M9 5l7 7-7 7"/>',
    menu: '<path d="M4 8h16M4 16h16"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
    moon: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    check: '<path d="M5 13l4 4L19 7"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    grid: '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/>',
    user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
    logout: '<path d="M9 4H5v16h4M14 8l4 4-4 4M18 12H9"/>',
    expand: '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
    compress: '<path d="M9 4v5H4M15 4v5h5M20 15h-5v5M4 15h5v5"/>',
    blur: '<circle cx="12" cy="12" r="4.2"/><path d="M12 3.2v2.2M12 18.6v2.2M3.2 12h2.2M18.6 12h2.2M5.8 5.8l1.6 1.6M16.6 16.6l1.6 1.6M18.2 5.8l-1.6 1.6M7.4 16.6l-1.6 1.6" stroke-dasharray="1.5 2.4"/>'
  };

  function icon(name, cls) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' +
      (cls ? ' class="' + cls + '"' : '') + '>' + (ICONS[name] || "") + "</svg>";
  }

  /* ---------- theme(本地偏好): dark / light / blur 三态循环 ------------- */
  var THEME_KEY = "pc.theme.v1";
  var THEMES = ["dark", "light", "blur"];
  var LB_BG_KEY = "pc.lbBg.v1";  /* 灯箱背景: solid / blur, 全局持久化 */
  var lbBg = "solid";
  try { var _lb = localStorage.getItem(LB_BG_KEY); if (_lb === "blur" || _lb === "solid") lbBg = _lb; } catch (e) {}
  var state = { theme: "dark", favs: { model: [], collection: [], photo: [] } };

  try {
    var saved = localStorage.getItem(THEME_KEY);
    if (THEMES.indexOf(saved) !== -1) state.theme = saved;
    else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) state.theme = "light";
  } catch (e) { /* storage unavailable */ }

  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", state.theme === "light" ? "#ffffff" : "#0c0d0f");
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      /* 顶栏钮三态循环: 黑→白→虚化; 设置页三段选择器同步 */
      var next = THEMES[(THEMES.indexOf(state.theme) + 1) % THEMES.length];
      b.innerHTML = icon(state.theme === "blur" ? "blur" : state.theme === "dark" ? "sun" : "moon");
      b.setAttribute("aria-label",
        next === "dark" ? t("Switch to dark theme")
        : next === "light" ? t("Switch to light theme")
        : t("Switch to blur theme"));
    });
    var sw = document.querySelector("[data-theme-switch]");
    if (sw) {
      sw.setAttribute("aria-checked", state.theme === "dark" ? "true" : "false");
      var lbl = document.querySelector("[data-theme-label]");
      if (lbl) lbl.textContent = state.theme === "dark" ? t("Gallery (dark)")
        : state.theme === "light" ? t("Editorial (light)") : t("Blur (cover)");
    }
    var seg = document.querySelector("[data-theme-seg]");
    if (seg) {
      seg.querySelectorAll("[data-theme-opt]").forEach(function (o) {
        o.setAttribute("aria-pressed", o.getAttribute("data-theme-opt") === state.theme ? "true" : "false");
      });
    }
  }

  function setTheme(v) {
    if (THEMES.indexOf(v) === -1 || v === state.theme) return;
    state.theme = v;
    try { localStorage.setItem(THEME_KEY, v); } catch (e) {}
    applyTheme();
    renderBlurLayer();
    /* 发现页在访前轮播已播: 切入虚化时垫底层直接跟当前轮播图,
       而不是 boot 注入的"今日封面"(两者可能不同图) */
    if (v === "blur" && heroBgSrc) {
      document.dispatchEvent(new CustomEvent("pc:hero-bg", { detail: { src: heroBgSrc } }));
    }
    document.dispatchEvent(new CustomEvent("pc:theme"));
  }

  function toggleTheme() {
    /* 顶栏钮: 三态循环 黑→白→虚化→黑 */
    setTheme(THEMES[(THEMES.indexOf(state.theme) + 1) % THEMES.length]);
  }

  /* ---------- 虚化垫底层(blur 主题) -----------------------------------
     整页背后垫一张放大模糊压暗的封面图(复用首页 hero__bg 配方):
     模特主页用头像, 写真详情用第一张图, 其他页面用首页精选封面。
     图源由服务端 boot_json.blur_src 按路径注入, 跨页导航自动更新。 */
  /* 预载缓存: 记录当前垫底图的就绪状态 */
  var preload = { src: "", ok: false };
  var heroBgSrc = ""; /* 发现页轮播当前图的 src(blur 主题垫底层跟随它) */

  function renderBlurLayer() {
    var el = document.querySelector("[data-page-blur]");
    if (!el) return;
    var src = BOOT.blur_src || "";
    /* 页面一打开就预载垫底图(不蜜主题是什么),
       等用户点切到虚化时图已在缓存, 点击即显不用等 */
    if (src && preload.src !== src) {
      preload.src = src;
      preload.ok = false;
      var img = new Image();
      img.onload = function () {
        if (preload.src !== src) return;
        preload.ok = true;
        if (state.theme === "blur") renderBlurLayer();
      };
      img.onerror = function () { if (preload.src === src) preload.ok = true; };
      img.src = src;
    }
    var on = state.theme === "blur" && src;
    el.dataset.on = on ? "true" : "false";
    if (!on) {
      /* 切出虚化: 把图摘下来, 回来时才走完整上墙路径 */
      el.removeAttribute("data-ready");
      var zoom = el.querySelector(".page-blur__zoom");
      var old = el.querySelector("img");
      if (old) old.remove();
      if (zoom) { zoom.style.transition = "none"; zoom.style.transform = ""; }
      return;
    }
    var zoomEl = el.querySelector(".page-blur__zoom");
    if (!zoomEl) { zoomEl = document.createElement("div"); zoomEl.className = "page-blur__zoom"; el.appendChild(zoomEl); }
    if (!el.querySelector("img")) {
      /* head 内联脚本可能已建好一张(首帧直出背景), 优先收养它,
         避免同一 URL 建两个 img 导致跨页时闪烁 */
      var adopted = document.head.querySelector("img[data-page-blur-img]");
      if (adopted) {
        adopted.removeAttribute("data-page-blur-img");
        zoomEl.appendChild(adopted);
        el.setAttribute("data-ready", "true");
        return;
      }
      var im = document.createElement("img");
      im.alt = "";
      if (preload.ok && preload.src === src) {
        im.src = src; /* 预载已完成, 直接上墙淡入 */
        zoomEl.appendChild(im);
        el.setAttribute("data-ready", "true");
      } else {
        /* 图未就绪: 挂上元素等 onload; 3 秒兑底强制显示,
           避免黑屏等太久(正常路径下预载早已完成) */
        im.onload = function () {
          if (im.parentNode === zoomEl) el.setAttribute("data-ready", "true");
        };
        im.src = src;
        zoomEl.appendChild(im);
        clearTimeout(renderBlurLayer._t);
        renderBlurLayer._t = setTimeout(function () {
          if (im.parentNode === zoomEl) el.setAttribute("data-ready", "true");
        }, 3000);
      }
    }
  }

  /* ---------- 首页轮播 ↔ blur 垫底层同步 -----------------------------
     发现页轮播每换一张图, 广播 pc:hero-bg; blur 主题下垫底层换上
     同一张图(同 hero 配方: 900 档已在页里, 这里收到的已是 2400 档,
     浏览器有缓存直接淡入)。整页一块背景, 与轮播无缝一体。
     非 blur 主题只做预载, 不动页面。 */
  document.addEventListener("pc:hero-bg", function (e) {
    var el = document.querySelector("[data-page-blur]");
    if (!el || !e.detail || !e.detail.src) return;
    var src = e.detail.src;
    heroBgSrc = src;
    if (state.theme !== "blur") return; /* 仅虚化模式需要整页同步 */
    var cur = el.querySelector("img");
    if (cur && cur.src === src) return;
    /* 轮播驱动的换图带缓落回弹; 首次上墙(切主题/进页)不带 */
    el.dataset.sync = "true";
    swapBlurImg(el, src);
  });

  function swapBlurImg(el, src) {
    var im = new Image();
    im.alt = "";
    im.onload = function () {
      if (state.theme !== "blur") return;
      var stale = el.querySelector("img");
      if (stale) stale.remove();
      var z = el.querySelector(".page-blur__zoom");
      if (!z) { z = document.createElement("div"); z.className = "page-blur__zoom"; el.appendChild(z); }
      z.appendChild(im);
      el.setAttribute("data-ready", "true");
      /* 回弹: 缩放钉在外层 zoom 容器(img 静止承载 blur 滤镜, 只栅格化
         一次), 先无过渡钉在放大档, 下一帧放回基础档走 1400ms 缓落
         (灯箱 backdrop 同款配方 —— 不钉直接换 src 会从中间值抖动) */
      if (el.dataset.sync === "true") {
        var zoom = el.querySelector(".page-blur__zoom");
        if (!zoom) return;
        zoom.style.transition = "none";
        zoom.style.transform = "scale(1.4)";
        requestAnimationFrame(function () {
          if (!zoom.parentNode || zoom.parentNode !== el) return;
          zoom.style.transition = "";
          zoom.style.transform = "";
        });
      }
    };
    im.src = src;
  }

  /* ---------- favourites(服务端)------------------------------------------ */
  var fav = {
    has: function (type, id) { return state.favs[type].indexOf(id) > -1; },
    toggle: function (type, id) {
      var list = state.favs[type];
      var i = list.indexOf(id);
      var added = i === -1;
      if (added) list.push(id); else list.splice(i, 1);
      document.dispatchEvent(new CustomEvent("pc:fav", { detail: { type: type, id: id, added: added } }));
      fetch("/api/favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ type: type, key: id, added: added })
      }).catch(function () { toast(t("Save failed — please retry")); });
      return added;
    },
    list: function (type) { return state.favs[type].slice(); },
    counts: function () {
      return { model: state.favs.model.length, collection: state.favs.collection.length, photo: state.favs.photo.length };
    },
    bind: function (root) {
      (root || document).querySelectorAll("[data-fav]").forEach(function (btn) {
        if (btn.dataset.favBound) return;
        btn.dataset.favBound = "1";
        sync(btn, btn.dataset.fav, btn.dataset.favKey);
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          var type = btn.dataset.fav;
          var id = btn.dataset.favKey;
          if (!id) return;
          var added = fav.toggle(type, id);
          sync(btn, type, id);
          toast(added ? t("Saved to favourites") : t("Removed from favourites"));
        });
      });
    }
  };

  function sync(btn, type, id) {
    var on = fav.has(type, id);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    var label = btn.querySelector("[data-fav-label]");
    if (label) label.textContent = on ? t("Saved") : t("Save");
    var sr = btn.querySelector(".sr");
    if (sr) sr.textContent = on ? t("Remove from favourites") : t("Add to favourites");
  }

  function syncAll() {
    document.querySelectorAll("[data-fav]").forEach(function (btn) {
      sync(btn, btn.dataset.fav, btn.dataset.favKey);
    });
    document.querySelectorAll("[data-fav-count]").forEach(function (el) {
      el.textContent = fav.counts()[el.dataset.favCount];
    });
    var dot = document.querySelector("[data-fav-dot]");
    if (dot) {
      var total = fav.counts().model + fav.counts().collection + fav.counts().photo;
      dot.hidden = total === 0;
    }
  }

  function loadFavs() {
    fetch("/api/favorites", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        ["model", "collection", "photo"].forEach(function (k) {
          if (Array.isArray(d[k])) state.favs[k] = d[k];
        });
        fav.bind();
        syncAll();
      })
      .catch(function () {});
  }

  /* ---------- toast ------------------------------------------------------ */
  var toastEl, toastTimer;
  function toast(msg) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "toast";
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      document.body.appendChild(toastEl);
    }
    toastEl.innerHTML = icon("check") + "<span>" + msg + "</span>";
    requestAnimationFrame(function () { toastEl.dataset.open = "true"; });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.dataset.open = "false"; }, 2200);
  }

  /* ---------- image reveal ----------------------------------------------
   * 图片一到就完整显示, 不做透明度淡入。淡入(半透明图叠在占位底上)
   * 在滚动场景会被反复触发, 视觉上就是「卡片闪」; skeleton 占位底
   * 保留在图下不动, 图到达即覆盖, 观感是「直接出现」而非「浮现」。 */
  function revealImages(root) {
    (root || document).querySelectorAll(".frame img:not([data-reveal])").forEach(function (img) {
      img.setAttribute("data-reveal", "1");
      img.classList.add("is-loaded");
      var f = img.parentElement;
      if (f) f.classList.remove("skeleton");
    });
  }

  /* ---------- chrome ----------------------------------------------------- */
  var NAV = [
    { href: "/", label: t("Discovery"), key: "discovery" },
    { href: "/models", label: t("Models"), key: "models" },
    { href: "/collections", label: t("Collections"), key: "collections" }
  ];

  function activeKey() {
    var p = BOOT.path || location.pathname;
    if (p === "/" || p === "") return "discovery";
    if (p.indexOf("/models") === 0) return "models";
    if (p.indexOf("/collections") === 0) return "collections";
    if (p.indexOf("/favorites") === 0) return "favorites";
    if (p.indexOf("/profile") === 0) return "profile";
    return "";
  }

  function renderChrome() {
    var page = activeKey();

    var header = document.querySelector("[data-header]");
    if (header) {
      /* 全站顶栏统一轻霜玻璃(同首页): 半透明深底 + backdrop-filter,
         前景文字/图标保持白;首页 hero 仍由 .shell--immersive 上移垫图 */
      header.className = "header header--immersive";
      header.innerHTML =
        '<div class="wrap header__inner">' +
        '<button class="icon-btn header__burger" type="button" data-drawer-open aria-label="' + t("Open menu") + '">' + icon("menu") + "</button>" +
        '<a class="wordmark" href="/">Photo&nbsp;<em>Collection</em></a>' +
        '<nav class="nav" aria-label="' + t("Primary") + '">' +
        NAV.map(function (n) {
          return '<a class="nav__link" href="' + n.href + '"' + (n.key === page ? ' aria-current="page"' : "") + ">" + n.label + "</a>";
        }).join("") +
        "</nav>" +
        '<div class="header__end">' +
        '<button class="icon-btn" type="button" data-search-open aria-label="' + t("Search the archive") + '">' + icon("search") + "</button>" +
        '<a class="icon-btn" href="/favorites" aria-label="' + t("Favourites") + '">' + icon("heart") +
        '<span class="icon-btn__dot" data-fav-dot hidden></span></a>' +
        '<button class="icon-btn" type="button" data-theme-toggle aria-label="' + t("Switch theme") + '"></button>' +
        '<a class="avatar-btn" href="/profile" aria-label="' + t("Your profile") + '">' +
        (ME.avatar
          ? '<img src="' + ME.avatar + '" alt="" width="30" height="30">'
          : '<span class="avatar-btn__initial">' + escapeHtml((ME.name || "?").charAt(0).toUpperCase()) + "</span>") +
        "</a>" +
        "</div></div>";
    }

    var drawer = document.querySelector("[data-drawer]");
    if (drawer) {
      drawer.innerHTML =
        '<div class="drawer__top">' +
        '<a class="wordmark" href="/">Photo&nbsp;<em>Collection</em></a>' +
        '<button class="icon-btn" type="button" data-drawer-close aria-label="' + t("Close menu") + '">' + icon("close") + "</button>" +
        "</div>" +
        '<nav class="drawer__nav" aria-label="' + t("Mobile") + '">' +
        NAV.concat([
          { href: "/favorites", label: t("Favourites"), key: "favorites" },
          { href: "/profile", label: t("Profile"), key: "profile" }
        ]).map(function (n) {
          return '<a class="drawer__link" href="' + n.href + '"' + (n.key === page ? ' aria-current="page"' : "") + ">" + n.label + "</a>";
        }).join("") +
        (ME.role === "admin" ? '<a class="drawer__link" href="/admin">' + t("Admin Dashboard") + "</a>" : "") +
        "</nav>" +
        '<div class="drawer__foot">' +
        '<button class="btn btn--ghost btn--sm" type="button" data-search-open>' + t("Search") + "</button>" +
        '<button class="btn btn--ghost btn--sm" type="button" data-theme-toggle>' +
        '<span data-theme-icon></span><span>' + t("Theme") + "</span></button>" +
        '<a class="btn btn--ghost btn--sm" href="/logout">' + t("Log out") + "</a>" +
        "</div>";
    }

    var search = document.querySelector("[data-search]");
    if (search) {
      search.innerHTML =
        '<div class="search__bar"><div class="wrap search__bar-inner">' +
        icon("search") +
        '<input class="search__input" type="search" data-search-input placeholder="' + t("Search models, collections, tags") + '" aria-label="' + t("Search") + '">' +
        '<button class="icon-btn" type="button" data-search-close aria-label="' + t("Close search") + '">' + icon("close") + "</button>" +
        "</div></div>" +
        '<div class="wrap search__body" data-search-results></div>';
    }

    var footer = document.querySelector("[data-footer]");
    if (footer) {
      var stats = (window.PB_BOOT && window.PB_BOOT.stats) || { collections: "—", models: "—" };
      var tags = (window.PB_BOOT && window.PB_BOOT.tags) || [];
      footer.className = "footer";
      footer.innerHTML =
        '<div class="wrap">' +
        '<div class="footer__top">' +
        "<div>" +
        '<p class="footer__wordmark">Photo&nbsp;<em>Collection</em></p>' +
        '<p class="footer__blurb">' + t("A digital archive of editorial photography. {c} collections, {m} models.", { c: stats.collections, m: stats.models }) + "</p>" +
        "</div>" +
        '<div><p class="footer__col-title">' + t("Browse") + "</p>" +
        '<a class="footer__link" href="/">' + t("Discovery") + "</a>" +
        '<a class="footer__link" href="/models">' + t("Models") + "</a>" +
        '<a class="footer__link" href="/collections">' + t("Collections") + "</a></div>" +
        '<div><p class="footer__col-title">' + t("Your archive") + "</p>" +
        '<a class="footer__link" href="/favorites">' + t("Favourites") + "</a>" +
        '<a class="footer__link" href="/profile">' + t("Profile") + "</a>" +
        '<a class="footer__link" href="/profile#settings">' + t("Settings") + "</a></div>" +
        '<div><p class="footer__col-title">' + t("Tags") + "</p>" +
        tags.slice(0, 4).map(function (t) {
          return '<a class="footer__link" href="/collections?tag=' + encodeURIComponent(t) + '">' + escapeHtml(t) + "</a>";
        }).join("") +
        "</div></div>" +
        '<div class="footer__bottom">' +
        "<span>© 2026 Photo Collection · v" + ((window.PB_BOOT && window.PB_BOOT.version) || "?") + "</span>" +
        "<span>" + t("All photographs are licensed to the archive.") + "</span>" +
        "</div></div>";
    }
  }

  /* ---------- search(服务端检索)------------------------------------------ */
  function renderSearchResults(payload) {
    var box = document.querySelector("[data-search-results]");
    if (!box) return;

    if (payload === null) {
      var suggestions = (window.PB_BOOT && window.PB_BOOT.suggestions) || ["Editorial", "Studio", "Outdoor"];
      box.innerHTML =
        '<div class="search__group">' +
        '<p class="search__group-title">' + t("Try a tag") + "</p>" +
        '<div class="chip-row">' +
        suggestions.map(function (s) {
          return '<button class="chip" type="button" data-search-suggest="' + escapeHtml(s) + '">' + escapeHtml(s) + "</button>";
        }).join("") +
        "</div></div>";
      return;
    }

    var total = payload.models.length + payload.collections.length + payload.tags.length;
    if (!total) {
      box.innerHTML =
        '<div class="state">' +
        '<h2 class="state__title">' + t("No results found.") + "</h2>" +
        '<p class="state__text">' + t("Nothing in the archive matches “{q}”. Try a broader term, or browse by tag.", { q: escapeHtml(payload.q) }) + "</p>" +
        '<a class="btn btn--ghost" href="/collections">' + t("Browse collections") + "</a>" +
        "</div>";
      return;
    }

    var html = "";
    if (payload.models.length) {
      html += '<div class="search__group"><p class="search__group-title">' + t("Models") + "</p>" +
        payload.models.map(function (m) {
          return '<a class="search-row" href="/models/' + m.slug + '">' +
            '<img class="search-row__thumb" src="' + m.thumb + '" alt="" loading="lazy">' +
            '<span><span class="search-row__name">' + escapeHtml(m.name) + "</span>" +
            '<span class="search-row__meta">' + escapeHtml((m.tags || []).join(", ")) + "</span></span>" +
            '<span class="search-row__end">' + t("{n} collections", { n: m.count }) + "</span></a>";
        }).join("") + "</div>";
    }
    if (payload.collections.length) {
      html += '<div class="search__group"><p class="search__group-title">' + t("Collections") + "</p>" +
        payload.collections.map(function (c) {
          return '<a class="search-row" href="/collections/' + c.slug + '">' +
            '<img class="search-row__thumb" src="' + c.thumb + '" alt="" loading="lazy">' +
            '<span><span class="search-row__name">' + escapeHtml(c.title) + "</span>" +
            '<span class="search-row__meta">' + escapeHtml(c.model_name) + " · " + t("{n} photos", { n: c.count }) + "</span></span>" +
            '<span class="search-row__end">' + escapeHtml(c.date || "") + "</span></a>";
        }).join("") + "</div>";
    }
    if (payload.tags.length) {
      html += '<div class="search__group"><p class="search__group-title">' + t("Tags") + "</p>" +
        payload.tags.map(function (t) {
          return '<a class="search-row" href="/collections?tag=' + encodeURIComponent(t) + '">' +
            '<span class="search-row__name">' + escapeHtml(t) + "</span></a>";
        }).join("") + "</div>";
    }
    box.innerHTML = html;
  }

  var searchSeq = 0;
  function runSearch(q) {
    var box = document.querySelector("[data-search-results]");
    if (!q.trim()) { renderSearchResults(null); return; }
    var seq = ++searchSeq;
    fetch("/api/search?q=" + encodeURIComponent(q), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && seq === searchSeq) renderSearchResults(d); })
      .catch(function () {});
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function openSearch() {
    var el = document.querySelector("[data-search]");
    if (!el) return;
    el.dataset.open = "true";
    document.body.classList.add("is-locked");
    renderSearchResults(null);
    var input = el.querySelector("[data-search-input]");
    if (input) { input.value = ""; setTimeout(function () { input.focus(); }, 60); }
  }

  function closeSearch() {
    var el = document.querySelector("[data-search]");
    if (!el) return;
    el.dataset.open = "false";
    document.body.classList.remove("is-locked");
  }

  /* ---------- lightbox -------------------------------------------------- */
  var LB_ZOOM = 1.5; /* 放大倍数: fit 尺寸 ×1.5(可调) */
  var lb = { photos: [], index: 0, title: "", collection: "", zoom: false, hi: false, el: null, bdFront: null, imgFront: null,
             pan: { x: 0, y: 0 }, dragging: false, dragMoved: false, dragStart: null, tstart: null };
  /* 主图双缓冲图层对: a/b 两张 img 交替。front = 最近一次揭示的层 */
  function lbImgPair() {
    var el = lb.el;
    var a = el.querySelector('[data-lb-img="a"]');
    var b = el.querySelector('[data-lb-img="b"]');
    var front = lb.imgFront === b ? b : a;
    return [front, front === a ? b : a];
  }

  /* 当前真正显示画面的层(ready=true): 交叉/加载等待期可能是前层,
     其余时刻即 front; 都未就绪(垫底显示中)返回 front */
  function lbVisibleImg() {
    var pair = lbImgPair();
    if (pair[0].dataset.ready === "true") return pair[0];
    if (pair[1].dataset.ready === "true") return pair[1];
    return pair[0];
  }

  function lightboxSrc(p, w) {
    if (!w) return "/media/" + p.file;             /* 真原图:下载 / 1:1 放大 */
    return "/t/s" + w + "/" + p.file + ".webp";    /* 短边档:竖图钳宽横图钳高,等比不裁 */
  }

  /* 灯箱显示档: 恒短边 2400, 与后端 PREHEAT_SHORT 一一对应。
     曾用屏宽判档(m*1.5<=2100 ? 1800 : 2400) —— 于是 1440px 以上的桌面全部
     落到 2400, 而 2400 当年不预热, 首开每张都要服务端现场解码 230~900ms。
     屏宽判档还让每种窗口尺寸各生成一个缓存档(2160/2268…), 档位漂移必须消灭。
     固定一档: 桌面全屏无差, 小屏/移动端只多下 20% 字节, 换来永远命中热缓存。
     短边语义(s 前缀): 竖图 2400×3600、横图 3600×2400, 4K 全屏两向都零上采样
     (旧钳宽档横图在 4K 要放大 1.2~1.6 倍)。
     注: 这里不乘 DPR —— 1:1 放大走真原图(见 upgradeOriginal)。 */
  var LB_W = 2400;
  /* 垫底/氛围档: 短边 900(与后端 WALL_W 一致)。注意 /t/s900/ 与网格页
     /t/900/ 是不同的缓存档(短边钳制 vs 钳宽), 服务器侧缓存互不相通 ——
     「网格页看过所以氛围层零等待」不成立, s900 首次切到必现一次网络往返。
     解法: 氛围档随导航预取(见 bdPrefetch), 切换时素材已在内存, 揭示即时 */
  var WALL_W = 900;

  function lightboxEl() {
    if (lb.el) return lb.el;
    var el = document.createElement("div");
    el.className = "lightbox";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", t("Photo viewer"));
    el.innerHTML =
      '<div class="lightbox__bar">' +
      '<span class="lightbox__title" data-lb-title></span>' +
      '<div class="lightbox__bar-end">' +
      '<button class="icon-btn" type="button" data-lb-close aria-label="' + t("Close viewer") + '">' + icon("close") + "</button>" +
      "</div></div>" +
      /* 氛围层双缓冲: 两块同式样交替, 新图永远在旧图之上淡入,
         旧图等新图完全不透明后再撤 —— 任何时刻至少一层完全不透明,
         结构上杜绝换图黑帧(单元素换 src 在重模糊下会有空帧)。
         外包一层容器, 层间 zIndex 交替不与顶/底栏(z-index:1)跨层比较 */
      '<div class="lightbox__bdwrap" aria-hidden="true">' +
      '<img class="lightbox__backdrop" data-lb-bd="a" alt="" decoding="async">' +
      '<img class="lightbox__backdrop" data-lb-bd="b" alt="" decoding="async">' +
      "</div>" +
      '<div class="lightbox__stage">' +
      /* 垫底层: 900 档先上屏撑住画面, 主图就绪后淡入盖住 */
      '<img class="lightbox__under" data-lb-under alt="" aria-hidden="true" decoding="async">' +
      '<button class="lightbox__nav lightbox__nav--prev" type="button" data-lb-prev aria-label="' + t("Previous photo") + '">' + icon("left") + "</button>" +
      /* 主图双缓冲(轮播同款定框结构): figure 定框(overflow:hidden, 按照片
         ar 取 contain 矩形, 永不缩放) + 内层 img 只做 settle 缩放 ≥1,
         溢出全被定框裁掉 —— 边缘静止, 残影从结构上不可能 */
      '<figure class="lightbox__img" data-lb-img="a"><img class="lightbox__photo" alt="" decoding="async" draggable="false"></figure>' +
      '<figure class="lightbox__img" data-lb-img="b"><img class="lightbox__photo" alt="" decoding="async" draggable="false"></figure>' +
      '<button class="lightbox__nav lightbox__nav--next" type="button" data-lb-next aria-label="' + t("Next photo") + '">' + icon("right") + "</button>" +
      "</div>" +
      '<div class="lightbox__foot">' +
      '<span class="lightbox__counter" data-lb-counter></span>' +
      '<div class="lightbox__foot-actions">' +
      '<button class="icon-btn" type="button" data-lb-fullscreen aria-pressed="false" title="' + t("Fullscreen") + '">' + icon("expand") + "</button>" +
      '<button class="icon-btn" type="button" data-lb-bg aria-pressed="' + (lbBg === "blur" ? "true" : "false") + '" title="' + t("Backdrop: blurred cover") + '">' + icon(lbBg === "blur" ? "blur" : "moon") + "</button>" +
      '<button class="fav" type="button" data-fav="photo" data-fav-key="" aria-pressed="false" title="' + t("Favourite photo") + '">' +
      icon("heart") + '<span class="sr">' + t("Add to favourites") + "</span></button>" +
      '<a class="btn btn--ghost btn--sm" data-lb-download download>' + icon("download") + '<span class="sr">' + t("Download") + "</span></a>" +
      "</div></div>" +
      '<div class="lightbox__progress"><i data-lb-progress></i></div>';
    document.body.appendChild(el);
    lb.el = el;

    el.querySelector("[data-lb-close]").addEventListener("click", close);
    el.querySelector("[data-lb-bg]").addEventListener("click", toggleBackdrop);
    el.querySelector("[data-lb-fullscreen]").addEventListener("click", toggleFullscreen);
    el.querySelector("[data-lb-prev]").addEventListener("click", function () { go(-1); });
    el.querySelector("[data-lb-next]").addEventListener("click", function () { go(1); });
    el.querySelectorAll("[data-lb-img]").forEach(function (fig) {
      fig.querySelector(".lightbox__photo").addEventListener("click", toggleZoom);
    });
    /* 点击背景空白关闭;拖拽后释放的 click 不算(dragMoved 守卫) */
    el.addEventListener("click", function (e) { if (e.target === el && !lb.dragMoved) close(); });

    /* 放大后按住拖拽平移(transform);未放大不拦截。
       监听挂在整个 lightbox 上: 竖图放大后图片下部会溢出 stage、
       被 foot 栏盖住, 只监听 stage 时那部分图拖不动。
       点击与拖拽靠移动阈值区分, 拖后释放的 click 不触发缩放/关闭 */
    var applyPan = function () {
      lbVisibleImg().style.transform =
        "translate(" + lb.pan.x + "px," + lb.pan.y + "px) scale(" + LB_ZOOM + ")";
    };
    var onDragMove = function (x, y) {
      if (!lb.dragging || !lb.zoom) return;
      var b = panBounds();
      var nx = lb.tstart.px + x - lb.tstart.x;
      var ny = lb.tstart.py + y - lb.tstart.y;
      /* 图随指针(grab 隐喻): y 上移(ny<0)受底部溢出量限制, 下移受顶部;
         x 同理。图完全在 stage 内时四向全 0, 居中锁死。 */
      lb.pan.x = nx > 0 ? Math.min(b.left, nx) : Math.max(-b.right, nx);
      lb.pan.y = ny > 0 ? Math.min(b.up, ny) : Math.max(-b.down, ny);
      lb.dragMoved = true;
      applyPan();
    };
    var onDragEnd = function () {
      if (!lb.dragging) return;
      lb.dragging = false;
      el.removeAttribute("data-dragging");
      /* click 事件在 mouseup/touchend 后触发;延后一拍清标志,让该次 click 被忽略 */
      setTimeout(function () { lb.dragMoved = false; }, 0);
    };
    el.addEventListener("mousedown", function (e) {
      if (!lb.zoom || e.button !== 0 || e.target.closest("button, a")) return;
      lb.dragging = true;
      lb.dragMoved = false;
      lb.tstart = { x: e.clientX, y: e.clientY, px: lb.pan.x, py: lb.pan.y };
      el.setAttribute("data-dragging", "true");
      e.preventDefault();
    });
    window.addEventListener("mousemove", function (e) { onDragMove(e.clientX, e.clientY); });
    window.addEventListener("mouseup", onDragEnd);

    /* 触摸拖拽平移(单指, 仅放大态)。swipe 切图与平移按 lb.zoom 分流;
       tap(无位移)仍产生 click 走 toggleZoom 缩回 —— touchstart 不能
       preventDefault(会吞掉后续 click), 滚动抑制交给 zoom 态 CSS 的
       touch-action:none + touchmove 的 preventDefault */
    el.addEventListener("touchstart", function (e) {
      if (!lb.zoom || e.touches.length !== 1 || e.target.closest("button, a")) return;
      lb.dragging = true;
      lb.dragMoved = false;
      lb.tstart = { x: e.touches[0].clientX, y: e.touches[0].clientY, px: lb.pan.x, py: lb.pan.y };
      el.setAttribute("data-dragging", "true");
    });

    el.addEventListener("touchmove", function (e) {
      if (!lb.dragging || !lb.zoom) return;
      e.preventDefault();
      onDragMove(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: false });
    el.addEventListener("touchend", function () { onDragEnd(); }, { passive: true });
    el.addEventListener("touchcancel", function () { onDragEnd(); }, { passive: true });

    /* swipe */
    var sx = 0, sy = 0, tracking = false;
    el.addEventListener("touchstart", function (e) {
      if (e.touches.length !== 1 || lb.zoom) return;
      sx = e.touches[0].clientX; sy = e.touches[0].clientY; tracking = true;
    }, { passive: true });
    el.addEventListener("touchend", function (e) {
      if (!tracking) return;
      tracking = false;
      var dx = e.changedTouches[0].clientX - sx;
      var dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
    }, { passive: true });

    /* 滚轮切换照片。三个场景的行为约定:
       1) 慢滚/精细滚轮: 单事件 delta 1~30, 跨事件累加攒阈值(40),
          武装态 800ms 无活动才清零, 不因停顿作废;
       2) 单次滚动(一 flick 连发数个事件, 手势可长达数百 ms): 首个过阈值
          的事件切一张, 之后 SUP_MS 抑制期内的事件**全部丢弃**。抑制窗必须
          盖住一个完整手势 —— 180ms 实测不够(稍长的滚动在抑制结束后, 同一
          手势的后续事件 delta≥100 立即又过阈值 → 一次滚切好几张), 取 400ms;
       3) 持续快滚: 抑制窗固定 SUP_MS 且**不被后续事件重置**(事件重置会
          让抑制期"滚多久吃多久"→ 整段快滚一张不切, 旧版败因), 到点重新
          武装, 节奏约每 400ms 一张。
       方向反转立即清账, 防上滚余波抵消下滚意图 */
    var SUP_MS = 400;
    var wheelAcc = 0, wheelSup = false, wheelSettle, wheelReset;
    el.addEventListener("wheel", function (e) {
      if (el.dataset.open !== "true" || lb.zoom) { wheelAcc = 0; return; }
      e.preventDefault();
      if (wheelSup) return;   /* 抑制期: 同一手势余波直接丢弃 */
      if (wheelAcc * e.deltaY < 0) wheelAcc = 0;
      wheelAcc += e.deltaY;
      clearTimeout(wheelReset);
      wheelReset = setTimeout(function () { wheelAcc = 0; }, 800);
      if (Math.abs(wheelAcc) < 40 || lb.photos.length < 2) return;
      var dir = wheelAcc > 0 ? 1 : -1;
      wheelAcc = 0;
      wheelSup = true;
      /* 定时器只在此刻设一次, 事件不重置它 —— SUP_MS 后必然重新武装 */
      wheelSettle = setTimeout(function () { wheelSup = false; wheelAcc = 0; }, SUP_MS);
      go(dir);
    }, { passive: false });

    document.addEventListener("keydown", function (e) {
      if (el.dataset.open !== "true") return;
      if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "Tab") trap(e, el);
    });

    return el;
  }

  function trap(e, el) {
    var f = el.querySelectorAll("button:not([disabled]), [href]");
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function open(opts) {
    var el = lightboxEl();
    lb.photos = opts.photos || [];
    lb.index = opts.index || 0;
    lb.title = opts.title || "";
    lb.collection = opts.collection || "";
    lb.zoom = false;
    lbShownUrl = "";   /* 重开不沿用上次舞台上的图, 走入场淡入 */
    el.dataset.open = "true";
    document.body.classList.add("is-locked");
    paint();
    /* 打开即预取 ±1(Immich initializePreloads): 用户浏览首图的 1~2s 里
       邻图 2400 已在下载, 首次翻页直接命中 */
    lbPrefetch();
    bdPrefetch();
    el.querySelector("[data-lb-close]").focus();
  }

  function close() {
    if (!lb.el) return;
    if (fullscreenEl()) document.exitFullscreen();
    lb.el.dataset.open = "false";
    document.body.classList.remove("is-locked");
    lbShownUrl = "";
  }

  function go(step) {
    if (!lb.photos.length) return;
    lb.index = (lb.index + step + lb.photos.length) % lb.photos.length;
    lb.zoom = false;
    paint();
    /* 导航瞬间沿方向补预取(Immich updateAfterNavigation), 不等当前图上屏
       —— 连翻时每步都提前一个身位。lbEntry 幂等, 已缓存的邻图零请求 */
    lbPrefetch();
    bdPrefetch();
  }

  /* 1:1 放大专用:按需加载真原图并替换(预览档用于 fit 显示已足够) */
  function upgradeOriginal(p, fig) {
    if (!p || lb.hi) return;
    var full = new Image();
    full.src = lightboxSrc(p);
    var swap = function () {
      if (lb.photos[lb.index] !== p || lbVisibleImg() !== fig) return;
      lb.hi = true;
      fig.querySelector(".lightbox__photo").src = full.src;
      fig.dataset.full = "true";
    };
    if (full.decode) { full.decode().then(swap, swap); }
    else { full.onload = swap; }
  }

  /* 平移边界: 放大态定框 transform = translate(pan) scale(LB_ZOOM),
     getBoundingClientRect 已含缩放与平移 —— 减去 pan 得 pan=0 时的
     缩放矩形, 与 stage 比对即四向溢出量(不可再除回 LB_ZOOM 还原 fit
     矩形: fit 恒在 stage 内, 溢出全 0, 平移会被钳死)。图没超出则锁 0。 */
  function panBounds() {
    var fig = lbVisibleImg();
    var st = lb.el.querySelector(".lightbox__stage");
    var stR = st.getBoundingClientRect();
    var r = fig.getBoundingClientRect();
    var pan = lb.pan || { x: 0, y: 0 };
    var baseTop = r.top - pan.y, baseBottom = r.bottom - pan.y;
    var baseLeft = r.left - pan.x, baseRight = r.right - pan.x;
    return {
      up: Math.max(0, stR.top - baseTop),         /* 图下移极限(顶部溢出量) */
      down: Math.max(0, baseBottom - stR.bottom), /* 图上移极限(底部溢出量) */
      left: Math.max(0, stR.left - baseLeft),      /* 图右移极限(左侧溢出量) */
      right: Math.max(0, baseRight - stR.right),   /* 图左移极限(右侧溢出量) */
    };
  }

  /* 退出放大:清除平移/缩放,回到 fit 显示 */
  function zoomOff(fig) {
    lb.zoom = false;
    lb.pan = { x: 0, y: 0 };
    fig.style.transform = "";
    fig.dataset.zoomed = "false";
    fig.querySelector(".lightbox__photo").style.cursor = "zoom-in";
    lb.el.dataset.zoom = "false";
  }

  /* 放大 = fit 显示 × LB_ZOOM,以 transform: scale 实现(从定框中心放大,
     布局尺寸不变 → 任何内核都保持居中, 不再依赖 grid 静态流溢出居中
     —— 移动内核会把超大的 static 网格项锚在起始角, 旧布局方案在移动端
     放大后图跑到左上角)。平移叠加在同一 transform 上。
     只作用于当前可见层(ready), 防止命中交叉/等待期的 idle 层 */
  function toggleZoom() {
    if (lb.dragMoved) return; /* 拖拽结束时的 click 不算缩放切换 */
    var fig = lbVisibleImg();
    if (lb.zoom) { zoomOff(fig); return; }
    lb.zoom = true;
    fig.dataset.zoomed = "true";
    fig.querySelector(".lightbox__photo").style.cursor = "grab";
    lb.el.dataset.zoom = "true";
    lb.pan = { x: 0, y: 0 };
    fig.style.transform = "scale(" + LB_ZOOM + ")";
    /* 放大才需要真原图 1:1 细节;fit 显示用高清版已足够 */
    upgradeOriginal(lb.photos[lb.index], fig);
  }

  /* 鼠标拖拽过程中抑制原生图片拖拽与文本选择 */

  /* 灯箱背景切换: solid 纯黑/纯白底 ↔ blur 当前图虚化垫底(轮播图同款配方)。
     全局持久化(localStorage), 所有页面共用 */
  function toggleBackdrop() {
    lbBg = lbBg === "blur" ? "solid" : "blur";
    try { localStorage.setItem(LB_BG_KEY, lbBg); } catch (e) {}
    paintBackdropBtn();
    paintBackdrop();
  }

  function paintBackdropBtn() {
    if (!lb.el) return;
    var b = lb.el.querySelector("[data-lb-bg]");
    if (!b) return;
    b.setAttribute("aria-pressed", lbBg === "blur" ? "true" : "false");
    b.innerHTML = icon(lbBg === "blur" ? "blur" : "moon");
    b.title = lbBg === "blur" ? t("Backdrop: blurred cover") : t("Backdrop: solid");
  }

  /* ---------- 灯箱全屏 -----------------------------------------------------
     浏览器 Fullscreen API 作用于灯箱元素本身;全屏态顶/底栏改悬浮在图上
     (图铺满视口, 栏不能还在顶部压出一行)。退出途径: 按钮、Esc/F11 原生
     退出、关灯箱 —— fullscreenchange 里统一刷新按钮态 */
  function fullscreenEl() {
    return document.fullscreenElement;
  }
  function toggleFullscreen() {
    if (fullscreenEl()) {
      document.exitFullscreen();
      return;
    }
    var request = lb.el.requestFullscreen || lb.el.webkitRequestFullscreen;
    if (request) request.call(lb.el);
  }
  function paintFullscreenBtn() {
    if (!lb.el) return;
    var b = lb.el.querySelector("[data-lb-fullscreen]");
    if (!b) return;
    var on = !!fullscreenEl();
    lb.el.dataset.fullscreen = on ? "true" : "false";
    b.setAttribute("aria-pressed", on ? "true" : "false");
    b.innerHTML = icon(on ? "compress" : "expand");
    b.title = on ? t("Exit fullscreen") : t("Fullscreen");
  }
  document.addEventListener("fullscreenchange", paintFullscreenBtn);

  function paintBackdrop() {
    if (!lb.el) return;
    var a = lb.el.querySelector('[data-lb-bd="a"]');
    var b = lb.el.querySelector('[data-lb-bd="b"]');
    if (!a || !b) return;
    var p = lb.photos[lb.index];
    if (lbBg !== "blur" || !p) {
      a.removeAttribute("src"); b.removeAttribute("src");
      a.dataset.ready = "false"; b.dataset.ready = "false";
      a.style.zIndex = ""; b.style.zIndex = "";
      lb.bdFront = null;
      lb.el.dataset.bg = "solid";
      return;
    }
    lb.el.dataset.bg = "blur";
    /* 氛围层用 s900 档: blur(46px) 下与 2400 无差。素材经 bdPrefetch
       预取进 bdCache(导航瞬间即发), 切换时通常已就绪 —— bdReady 直接
       resolve, 揭示零等待; 未命中预取(深跳/首开)时才等一次网络往返 */
    var src = lightboxSrc(p, WALL_W);
    var front = lb.bdFront && lb.bdFront.dataset.ready === "true" ? lb.bdFront : null;
    if (front && front.dataset.src === src) return;   /* 同图幂等 */
    /* 双缓冲: 新图加载到非前图层, 就绪后置顶淡入; 旧前图层等新层
       完全不透明后再撤。换图瞬间旧氛围始终铺在屏上, 黑帧不可能出现 */
    var back = front === a ? b : a;
    var reveal = function () {
      if (back.dataset.src !== src) return;                    /* 已被更新的加载覆盖 */
      if (lbBg !== "blur" || lb.photos[lb.index] !== p) return; /* stale */
      /* 复用层归零: 层被复用时 transform 可能停在回涨半路(回涨 1400ms
         > 撤层宽限 650ms)甚至已是 none, 直接置 ready 的过渡会从近 1 处
         起步 = 回弹消失(首层必现动效、后续切换全无的根因)。
         无过渡重置到 scale(1.2) 后, 必须隔一个 rAF(而非仅 reflow)再
         恢复过渡置 ready —— 同帧"重置→置 ready"会让浏览器把过渡起点
         算在重置前的计算样式上, 起步值随机(实测 1.03~1.25 抖动) */
      back.style.transition = "none";
      back.style.transform = "scale(1.2)";
      back.style.opacity = "0";
      requestAnimationFrame(function () {
        if (back.dataset.src !== src) return;                    /* 已被更新的加载覆盖 */
        if (lbBg !== "blur" || lb.photos[lb.index] !== p) return; /* stale */
        back.style.transition = "";
        back.style.transform = "";
        back.style.opacity = "";
        back.style.zIndex = "2";
        if (front) front.style.zIndex = "1";
        back.dataset.ready = "true";
        lb.bdFront = back;
        if (front) setTimeout(function () {
          /* 期间未被新一轮换前 → 撤旧层(在新层之下淡出, 不可见);
             ready=false 让它回涨 1.2, 与新层缓落互为镜像 */
          if (lb.bdFront === back) { front.dataset.ready = "false"; front.style.zIndex = ""; }
        }, 650);
      });
    };
    back.dataset.src = src;
    /* 揭示素材统一走 bdReady(bdCache 持有 Image, decode 完的位图常驻):
       预取命中 → promise 已 resolve, 稍作停顿即揭示; 未命中 → 用预取
       同一个请求, 不再像旧实现那样往 <img> 上挂 onload 第二次下载。
       揭示前停 100ms: 预取后揭示是瞬时的, 快速翻页时背景跟着照片跳
       反而显得急躁, 给一个呼吸感; 连翻时由 reveal 内 stale 守卫丢弃
       过期的延迟揭示(层与照片双重比对), 旧背景不会迟到刷屏 */
    bdReady(src).then(function (e) {
      if (!e || back.dataset.src !== src) return;
      setTimeout(function () {
        if (back.dataset.src !== src) return;
        if (lbBg !== "blur" || lb.photos[lb.index] !== p) return;
        back.src = e.img.src;   /* 同 URL, 命中 bdCache/HTTP 缓存, 无网络 */
        reveal();
      }, 100);
    });
  }

  /* ---------- 灯箱图 LRU --------------------------------------------------
     有界且**持有 Image 对象**: 只记 URL 的话, 预取的 Image 一出作用域就被 GC,
     解码位图随之释放, 翻回去要重新解码 —— 这是翻页体感最差的一条。
     2400 档解码位图约 30MB/张, 上限据此取, 再大就是拿内存换命中。 */
  var LB_CACHE_MAX = 6;
  var lbCache = {};
  var lbCacheOrder = [];
  var lbShownUrl = "";   /* 舞台上已有的图: 有 → 切图不抹白, 直接换 src */
  var lbHoldUrl = "";    /* 正在加载的当前图: 从创建 entry 到上屏前也受 LRU 保护
                            (go() 里预取紧随其后, 若只护 lbShownUrl 则旧图受护、
                            新图反遭淘汰, 丢掉刚解码的位图) */
  var lbSeq = 0;         /* 连翻时的过期响应守卫 */

  function lbEntry(u) {
    var e = lbCache[u];
    if (e) return e;
    e = { img: new Image(), ready: false, p: null };
    lbCache[u] = e;
    lbCacheOrder.push(u);
    for (var i = 0; i < lbCacheOrder.length && Object.keys(lbCache).length > LB_CACHE_MAX;) {
      var old = lbCacheOrder[i];
      /* 新进来的、正上屏的、正在加载的都不淘汰 */
      if (old === u || old === lbShownUrl || old === lbHoldUrl) { i++; continue; }
      lbCacheOrder.splice(i, 1);
      delete lbCache[old];
    }
    return e;
  }

  /* 用 decode() 而非 onload: onload 只代表字节到齐, 真正上屏时主线程还要
     解码 2400 档的 8.6MP —— 那才是切图卡顿的来源。失败不缓存 promise,
     下次翻到这张会重试。 */
  function lbReady(u) {
    var e = lbEntry(u);
    if (e.ready) return Promise.resolve(e);
    if (e.p) return e.p;
    var img = e.img;
    if (!img.src) img.src = u;
    var w = img.decode ? img.decode() : new Promise(function (res, rej) {
      img.onload = res; img.onerror = rej;
    });
    e.p = w.then(function () {
      e.ready = true; e.p = null; return e;
    }, function () { e.p = null; return null; });
    return e.p;
  }

  /* 邻图预取: 在 open()/go() 导航瞬间调用(Immich initializePreloads /
     updateAfterNavigation 时机), 让邻图下载解码与用户看图的时间重叠;
     不在当前图 onready 后才发。lbEntry 幂等, 已就绪的邻图零开销,
     故双向 ±1 固定预取即可, 不需方向取消(每步净新增下i仅为 1 张)。 */
  function lbPrefetch() {
    var n = lb.photos.length;
    if (n < 2) return;
    [1, -1].forEach(function (d) {
      var q = lb.photos[(lb.index + d + n) % n];
      if (q) lbReady(lightboxSrc(q, LB_W));
    });
  }

  /* ---------- 氛围层素材 LRU ----------------------------------------------
     与主图 LRU 分开: 主图 2400 档解码位图 ~30MB/张, 上限 6; s900 档
     位图 ~4MB/张, 预取 ±2 已绰绰有余。分开的目的是互不挤占 —— 混用
     同一个 LRU 时连翻会让 2400 档把 s900 冲掉, 翻回去又要重新请求 */
  var BD_CACHE_MAX = 8;
  var bdCache = {};
  var bdCacheOrder = [];

  function bdEntry(u) {
    var e = bdCache[u];
    if (e) return e;
    e = { img: new Image(), ready: false, p: null };
    bdCache[u] = e;
    bdCacheOrder.push(u);
    for (var i = 0; i < bdCacheOrder.length && Object.keys(bdCache).length > BD_CACHE_MAX;) {
      var old = bdCacheOrder[i];
      if (old === u) { i++; continue; }
      bdCacheOrder.splice(i, 1);
      delete bdCache[old];
    }
    return e;
  }

  function bdReady(u) {
    var e = bdEntry(u);
    if (e.ready) return Promise.resolve(e);
    if (e.p) return e.p;
    var img = e.img;
    if (!img.src) img.src = u;
    var w = img.decode ? img.decode() : new Promise(function (res, rej) {
      img.onload = res; img.onerror = rej;
    });
    e.p = w.then(function () {
      e.ready = true; e.p = null; return e;
    }, function () { e.p = null; return null; });
    return e.p;
  }

  /* 氛围档预取: 与 lbPrefetch 同时机(导航瞬间), 覆盖当前 + 双向 ±2。
     ±2 而非 ±1: 连翻时用户看到的是「上一张的虚化」, 预取到 ±2 才能保证
     快速连翻时下一张的氛围素材也已在内存 */
  function bdPrefetch() {
    var n = lb.photos.length;
    if (!n) return;
    [0, 1, -1, 2, -2].forEach(function (d) {
      var q = lb.photos[(lb.index + d + n) % n];
      if (q) bdReady(lightboxSrc(q, WALL_W));
    });
  }

  function paint() {
    var el = lb.el;
    if (!el) return;
    var p = lb.photos[lb.index];
    if (!p) return;
    /* 双缓冲(轮播同款定框结构): 新图载入 idle 定框淡入 + 框内照片缓落
       (1.015→1); 前层(旧画面)转离场 —— 镜像回涨 + 淡化, 交叉无空帧。
       首开(舞台无画面)只走入场, 无交叉。img/fig = 定框 figure,
       照片是框内 .lightbox__photo */
    var pair = lbImgPair();
    var fig = pair[1], prev = pair[0];
    var photo = fig.querySelector(".lightbox__photo");
    var first = !lbShownUrl;
    fig.dataset.zoomed = "false";
    fig.dataset.full = "false"; /* 视图上屏后置 true(预览档即终档) */
    lb.hi = false;              /* 切图后真原图需重新按需加载 */
    lb.zoom = false;
    lb.pan = { x: 0, y: 0 };
    fig.style.transform = "";   /* 清除放大模式平移/缩放与层序 */
    fig.style.zIndex = "";
    el.dataset.zoom = "false"; /* 切图/重开时退出放大模式(容器+图同步复位) */
    photo.style.cursor = "zoom-in";
    photo.alt = lb.title ? t("{title} — photo {n}", { title: lb.title, n: lb.index + 1 }) : t("Photo {n}", { n: lb.index + 1 });
    /* --ar 先按入库元数据预置(定框矩形立即就位); 揭示时再按解码尺寸
       校正一次(元数据缺失时兜底), 见下方 reveal */
    fig.style.setProperty("--ar",
      (p.w && p.h ? p.w / p.h : (photo.naturalWidth && photo.naturalHeight)
        ? photo.naturalWidth / photo.naturalHeight : 0.66).toFixed(4));
    /* 离场层复位残留(平移/缩放态), src 保留 —— 交叉期间它就是当前画面 */
    prev.style.transform = "";
    prev.style.zIndex = "";
    prev.dataset.zoomed = "false";
    prev.querySelector(".lightbox__photo").style.cursor = "zoom-in";
    prev.querySelector(".lightbox__photo").alt = "";

    /* 垫底层先行: 900 档与网格页同 URL 必命中 HTTP 缓存, 同步换上,
       主图就绪前舞台始终有画面; dataset.src 守卫丢弃连翻时的过期 onload */
    var under = el.querySelector("[data-lb-under]");
    var uSrc = lightboxSrc(p, WALL_W);
    if (under.dataset.src !== uSrc) {
      under.dataset.src = uSrc;
      under.dataset.ready = "false";
      under.src = uSrc;
      under.onload = function () {
        if (under.dataset.src !== uSrc) return;
        under.dataset.ready = "true";
        /* 冻结帧兜底: 垫底已就位而 2400 迟迟不揭示时, 旧层还挂着上一张
           —— 120ms 宽限后淡出旧层露出垫底(900 新图), 替代卡住的旧帧 */
        setTimeout(function () {
          if (seq !== lbSeq || lbShownUrl === url) return;
          if (el.dataset.zoom === "true") return;
          prev.dataset.ready = "false";
        }, 120);
      };
    }
    paintBackdrop();   /* 氛围层同为 900 档, 立即出现, 不等主图 */

    /* 主图终档 2400(服务端已预热; 未命中时也只生成这一档, 不再有二次升级);
       从不取 24MP 原图全尺寸解码。预取已上移到 open()/go() 导航瞬间 */
    var url = lightboxSrc(p, LB_W);
    lbHoldUrl = url;
    var seq = ++lbSeq;
    lbReady(url).then(function (e) {
      if (!e || seq !== lbSeq || lb.photos[lb.index] !== p) return;
      if (lbImgPair()[1] !== fig) return;   /* 已被更新一轮的揭示覆盖 */
      /* 揭示前按解码尺寸校正 --ar(元数据缺失时兜底; 定框矩形必须与
         2400 档 contain 矩形严格一致, 缩放溢出才会被完整裁在框内) */
      var nw = e.img.naturalWidth, nh = e.img.naturalHeight;
      if (nw && nh) fig.style.setProperty("--ar", (nw / nh).toFixed(4));
      photo.src = url;
      fig.dataset.full = "true"; /* LB_W 即终档, 免升级 */
      lbShownUrl = url;
      lb.imgFront = fig;
      if (!first) {
        /* 交叉: 新层置于旧层之上淡入, 旧层镜像回涨+淡化。
           层序: 入场内联 z2 > 离场类 z1(.lightbox__img[data-departing]);
           离场毕撤标记与内联层序, 归位为 idle */
        prev.dataset.departing = "true";
        fig.style.zIndex = "2";
        setTimeout(function () {
          if (lb.imgFront === fig && prev.dataset.departing === "true") {
            prev.removeAttribute("data-departing");
            fig.style.zIndex = "";
          }
        }, 680);
      }
      fig.dataset.ready = "true";
      prev.dataset.ready = "false";
      /* 新层已接住画面, 垫底层随即撤去; 若 2400 加载失败, 兜底逻辑
         已让垫底(900 新图)可见 → 降级为低清而非旧图/空屏 */
      under.dataset.ready = "false";
    });

    var title = el.querySelector("[data-lb-title]");
    title.textContent = lb.title || "";
    el.querySelector("[data-lb-counter]").textContent =
      String(lb.index + 1).padStart(2, "0") + " / " + String(lb.photos.length).padStart(2, "0");
    el.querySelector("[data-lb-progress]").style.width =
      ((lb.index + 1) / lb.photos.length) * 100 + "%";
    el.querySelector("[data-lb-prev]").disabled = lb.photos.length < 2;
    el.querySelector("[data-lb-next]").disabled = lb.photos.length < 2;

    /* 收藏键随照片切换;下载指向原图 */
    var fb = el.querySelector("[data-fav]");
    fb.dataset.fav = "photo";
    fb.dataset.favKey = lb.collection + ":" + lb.index;
    sync(fb, "photo", fb.dataset.favKey);
    var dl = el.querySelector("[data-lb-download]");
    dl.setAttribute("href", lightboxSrc(p));
    dl.setAttribute("download", (p.file || "").split("/").pop());
  }

  /* ---------- justified photo wall -------------------------------------- */
  /* 按行排序且无缝拼接: 先按目标行高估算总行数,再把图片按累计宽度中点
     均衡分到每一行,每行等高缩放至铺满容器宽 — 含末行,无行尾空白。
     每行末张用 flexGrow 吸收取整余量,右缘严格对齐。 */
  function targetRowHeight(w) { return w > 1180 ? 345 : w > 760 ? 365 : 255; }

  function layoutPhotoWall(root) {
    (root || document).querySelectorAll(".masonry--photos").forEach(function (wall) {
      var tiles = Array.prototype.filter.call(wall.children, function (el) {
        return el.classList.contains("photo-tile");
      });
      if (!tiles.length) return;

      /* 读取每张的宽高比(真实尺寸 → 模板 aspect-ratio 兑底) */
      var photos = tiles.map(function (tile) {
        var ar = 2 / 3;
        var img = tile.querySelector("img");
        if (img && img.naturalWidth && img.naturalHeight) {
          ar = img.naturalWidth / img.naturalHeight;
        } else {
          var f = tile.querySelector(".frame");
          if (f && f.style.aspectRatio) {
            var m = f.style.aspectRatio.split("/");
            if (m.length === 2 && +m[0] > 0) ar = +m[0] / +m[1];
          }
        }
        return { tile: tile, ar: ar };
      });

      var gap = 14;
      function relayout() {
        var avail = wall.clientWidth;
        if (!avail) return; /* 收藏页隐藏面板: 展示时 ResizeObserver 再触发 */
        var targetH = targetRowHeight(avail);
        var n = photos.length;

        /* 每张在目标行高下的占位宽(含列间距) → 估算行数,行数一定后
           末行与其他行一样按铺满分配,不再留白 */
        var slots = photos.map(function (p, i) { return targetH * p.ar + (i ? gap : 0); });
        var totalW = slots.reduce(function (s, x) { return s + x; }, 0);
        var R = Math.max(1, Math.round(totalW / (avail + gap)));
        var chunk = totalW / R;

        /* 中点归属: 第 i 张按累计宽度中点落入第 floor(mid/chunk) 行,
           各行宽度都接近容器宽,高度都贴近目标行高 */
        var acc = 0;
        var rows = [[]];
        for (var i = 0; i < n; i++) {
          var r = Math.min(R - 1, Math.floor((acc + slots[i] / 2) / chunk));
          while (rows.length <= r) rows.push([]);
          rows[r].push(photos[i]);
          acc += slots[i];
        }

        rows.forEach(function (row) {
          var A = row.reduce(function (s, p) { return s + p.ar; }, 0);
          var h = (avail - gap * (row.length - 1)) / A;
          var capped = h > targetH * 1.75; /* 极端比例兑底: 单行过高时封顶 */
          if (capped) h = targetH * 1.75;
          var sumW = 0;
          row.forEach(function (p) { sumW += Math.floor(h * p.ar); });
          row.forEach(function (p, idx) {
            var t = p.tile;
            t.style.width = Math.floor(h * p.ar) + "px";
            t.style.flexGrow = !capped && idx === row.length - 1 ? "1" : "";
            t.style.marginRight = "";
            t.style.marginInline = "";
            var frame = t.firstElementChild;
            if (frame) frame.style.height = Math.round(h) + "px";
          });
          if (capped) {
            if (row.length === 1) {
              row[0].tile.style.marginInline = "auto"; /* 单张全景居中 */
            } else {
              /* 封顶行剩余宽度均摊进图间距,行仍铺满,观感刻意而非残缺 */
              var extra = (avail - sumW - gap * (row.length - 1)) / (row.length - 1);
              row.slice(0, -1).forEach(function (p) {
                p.tile.style.marginRight = extra + "px";
              });
            }
          }
        });
      }

      relayout();
      if (window.ResizeObserver) {
        if (wall.__photoRO) wall.__photoRO.disconnect();
        var ro = new ResizeObserver(function () { relayout(); });
        ro.observe(wall);
        wall.__photoRO = ro;
      } else {
        window.addEventListener("resize", relayout);
      }
    });
  }

  /* ---------- masonry binding ------------------------------------------- */
  function bindPhotoTiles(root) {
    var data = window.PB_DATA;
    if (!data || !data.photos) return;
    (root || document).querySelectorAll("[data-photo-index]").forEach(function (tile) {
      if (tile.dataset.tileBound) return;
      tile.dataset.tileBound = "1";
      tile.addEventListener("click", function () {
        lb.returnFocus = tile;
        open({
          photos: data.photos,
          index: Number(tile.dataset.photoIndex),
          title: data.title + " — " + (data.model_name || ""),
          collection: data.slug
        });
      });
    });
  }

  /* ---------- chrome events --------------------------------------------- */
  function bindChrome() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest("[data-theme-toggle]")) { toggleTheme(); return; }
      var topt = t.closest("[data-theme-opt]");
      if (topt) { setTheme(topt.getAttribute("data-theme-opt")); return; }
      if (t.closest("[data-theme-switch]")) { toggleTheme(); return; }
      if (t.closest("[data-search-open]")) { closeDrawer(); openSearch(); return; }
      if (t.closest("[data-search-close]")) { closeSearch(); return; }
      if (t.closest("[data-drawer-open]")) { openDrawer(); return; }
      if (t.closest("[data-drawer-close]")) { closeDrawer(); return; }
      var sug = t.closest("[data-search-suggest]");
      if (sug) {
        var input = document.querySelector("[data-search-input]");
        input.value = sug.dataset.searchSuggest;
        runSearch(input.value);
        input.focus();
        return;
      }
      if (t.closest("[data-download-all]")) {
        /* 打包下载为设计稿预留(M4 导入管线后评估) */
        toast(t("Archive export is coming soon"));
        return;
      }
    });

    var debounce;
    document.addEventListener("input", function (e) {
      if (e.target.matches("[data-search-input]")) {
        clearTimeout(debounce);
        var v = e.target.value;
        debounce = setTimeout(function () { runSearch(v); }, 200);
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeSearch(); closeDrawer(); }
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openSearch(); }
    });

    document.addEventListener("pc:fav", function (e) {
      document.querySelectorAll('[data-fav="' + e.detail.type + '"][data-fav-key="' + e.detail.id + '"]')
        .forEach(function (btn) { sync(btn, e.detail.type, e.detail.id); });
      syncAll();
    });

    /* 滚动进行中给 <html> 挂 is-scrolling: CSS 侧抑制 hover 缩放/浮层,
       避免 Safari 内容经过静止指针时反复触发缩放过渡(卡片闪烁) */
    var scrollTimer = 0;
    window.addEventListener("scroll", function () {
      document.documentElement.classList.add("is-scrolling");
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () {
        document.documentElement.classList.remove("is-scrolling");
      }, 160);
    }, { passive: true });

    window.addEventListener("scroll", function () {
      var bar = document.querySelector("[data-sticky-bar]");
      if (!bar) return;
      var trigger = document.querySelector("[data-sticky-trigger]");
      var y = trigger ? trigger.getBoundingClientRect().bottom : 0;
      bar.dataset.visible = y < 64 ? "true" : "false";
    }, { passive: true });
  }

  function openDrawer() {
    var d = document.querySelector("[data-drawer]");
    if (!d) return;
    d.dataset.open = "true";
    document.body.classList.add("is-locked");
  }
  function closeDrawer() {
    var d = document.querySelector("[data-drawer]");
    if (!d) return;
    d.dataset.open = "false";
    document.body.classList.remove("is-locked");
  }

  /* ---------- boot ------------------------------------------------------ */
  function boot() {
    applyTheme();
    renderChrome();
    applyTheme(); /* theme buttons live in chrome */
    renderBlurLayer();
    bindChrome();
    fav.bind();
    syncAll();
    bindPhotoTiles();
    layoutPhotoWall();
    revealImages();
    loadFavs();
    watchForNewMedia();
  }

  /* Anything the pages render later (filters, load more, tab switches) still
     needs its placeholder handed over, so watch the tree rather than asking
     every page to remember. */
  function watchForNewMedia() {
    if (!window.MutationObserver) return;
    var queued = false;
    var mo = new MutationObserver(function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {
        queued = false;
        revealImages();
        layoutPhotoWall();
        fav.bind();
        syncAll();
        bindPhotoTiles();
        renderBlurLayer(); /* 设置页选择器等新节点可能带主题钮 */
      });
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  return {
    icon: icon,
    toast: toast,
    t: t,
    fav: fav,
    lightbox: { open: open, close: close },
    bindPhotoTiles: bindPhotoTiles,
    layoutPhotoWall: layoutPhotoWall,
    revealImages: revealImages,
    escapeHtml: escapeHtml,
    setTheme: setTheme,
    state: state
  };
})();
