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
    logout: '<path d="M9 4H5v16h4M14 8l4 4-4 4M18 12H9"/>'
  };

  function icon(name, cls) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' +
      (cls ? ' class="' + cls + '"' : '') + '>' + (ICONS[name] || "") + "</svg>";
  }

  /* ---------- theme(本地偏好)-------------------------------------------- */
  var THEME_KEY = "pc.theme.v1";
  var state = { theme: "dark", favs: { model: [], collection: [], photo: [] } };

  try {
    var saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") state.theme = saved;
    else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) state.theme = "light";
  } catch (e) { /* storage unavailable */ }

  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", state.theme === "dark" ? "#0c0d0f" : "#ffffff");
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.innerHTML = icon(state.theme === "dark" ? "sun" : "moon");
      b.setAttribute("aria-label", state.theme === "dark" ? t("Switch to light theme") : t("Switch to dark theme"));
    });
    var sw = document.querySelector("[data-theme-switch]");
    if (sw) {
      sw.setAttribute("aria-checked", state.theme === "dark" ? "true" : "false");
      var lbl = document.querySelector("[data-theme-label]");
      if (lbl) lbl.textContent = state.theme === "dark" ? t("Gallery (dark)") : t("Editorial (light)");
    }
  }

  function toggleTheme() {
    state.theme = state.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, state.theme); } catch (e) {}
    applyTheme();
    document.dispatchEvent(new CustomEvent("pc:theme"));
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

  /* ---------- image reveal ---------------------------------------------- */
  function revealImages(root) {
    (root || document).querySelectorAll(".frame img:not([data-reveal])").forEach(function (img) {
      img.setAttribute("data-reveal", "1");
      function done() {
        img.classList.add("is-loaded");
        var f = img.parentElement;
        if (f) f.classList.remove("skeleton");
      }
      if (img.complete && img.naturalWidth > 0) done();
      else {
        img.addEventListener("load", done, { once: true });
        img.addEventListener("error", done, { once: true });
      }
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
      header.className = "header";
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
        '<a class="avatar-btn" href="/profile" aria-label="' + t("Your profile") + '"><span class="avatar-btn__initial">' +
        escapeHtml((ME.name || "?").charAt(0).toUpperCase()) + "</span></a>" +
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
        "<span>© 2026 Photo Collection</span>" +
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
  var lb = { photos: [], index: 0, title: "", collection: "", zoom: false, hi: false, el: null };

  function lightboxSrc(p, w) {
    if (!w) return "/media/" + p.file;             /* 真原图:下载 / 1:1 放大 */
    return "/t/" + w + "/" + p.file + ".webp";     /* 缩放版:服务端只缩不放,磁盘缓存 */
  }

  /* 高清版目标宽:铺满最长边 ×1.5,夹在 [1800,2400] —— 24MP 原图缩到此尺寸
     后与真原图在屏幕上肉眼无差,但体积从 10–25MB 降到约 1–2MB */
  function hiWidth() {
    var m = Math.max(window.innerWidth || 0, window.innerHeight || 0);
    return Math.min(2400, Math.max(1800, Math.round(m * 1.5)));
  }

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
      '<div class="lightbox__stage">' +
      '<button class="lightbox__nav lightbox__nav--prev" type="button" data-lb-prev aria-label="' + t("Previous photo") + '">' + icon("left") + "</button>" +
      '<img class="lightbox__img" data-lb-img alt="">' +
      '<button class="lightbox__nav lightbox__nav--next" type="button" data-lb-next aria-label="' + t("Next photo") + '">' + icon("right") + "</button>" +
      "</div>" +
      '<div class="lightbox__foot">' +
      '<span class="lightbox__counter" data-lb-counter></span>' +
      '<div class="lightbox__foot-actions">' +
      '<button class="fav" type="button" data-fav="photo" data-fav-key="" aria-pressed="false" title="' + t("Favourite photo") + '">' +
      icon("heart") + '<span data-fav-label>' + t("Save") + '</span><span class="sr">' + t("Add to favourites") + "</span></button>" +
      '<a class="btn btn--ghost btn--sm" data-lb-download download>' + icon("download") + "<span>" + t("Download") + "</span></a>" +
      "</div></div>" +
      '<div class="lightbox__progress"><i data-lb-progress></i></div>';
    document.body.appendChild(el);
    lb.el = el;

    el.querySelector("[data-lb-close]").addEventListener("click", close);
    el.querySelector("[data-lb-prev]").addEventListener("click", function () { go(-1); });
    el.querySelector("[data-lb-next]").addEventListener("click", function () { go(1); });
    el.querySelector("[data-lb-img]").addEventListener("click", toggleZoom);
    el.addEventListener("click", function (e) { if (e.target === el) close(); });

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
    el.dataset.open = "true";
    document.body.classList.add("is-locked");
    paint();
    el.querySelector("[data-lb-close]").focus();
  }

  function close() {
    if (!lb.el) return;
    lb.el.dataset.open = "false";
    document.body.classList.remove("is-locked");
  }

  function go(step) {
    if (!lb.photos.length) return;
    lb.index = (lb.index + step + lb.photos.length) % lb.photos.length;
    lb.zoom = false;
    paint();
  }

  /* 高清升级:后台加载 ≤2400w 高清版(约 1–2MB),异步解码完才上屏(不闪烁、
     不卡顿);decode() 不阻塞主线程,老浏览器回退 onload。
     过期竞态防护:加载期间已切走则丢弃。真原图(10–25MB)仅在
     1:1 放大时由 upgradeOriginal 按需加载 */
  function upgradeFull(p, img) {
    if (img.dataset.full === "true" || !p) return;
    var hi = new Image();
    hi.src = lightboxSrc(p, hiWidth());
    var swap = function () {
      if (lb.photos[lb.index] !== p || img.dataset.full === "true") return;
      img.src = hi.src;
      img.dataset.full = "true";
    };
    if (hi.decode) { hi.decode().then(swap, swap); }
    else { hi.onload = swap; }
  }

  /* 1:1 放大专用:按需加载真原图并替换(高清版用于 fit 显示已足够) */
  function upgradeOriginal(p, img) {
    if (!p || lb.hi) return;
    var full = new Image();
    full.src = lightboxSrc(p);
    var swap = function () {
      if (lb.photos[lb.index] !== p) return;
      lb.hi = true;
      img.src = full.src;
      img.dataset.full = "true";
    };
    if (full.decode) { full.decode().then(swap, swap); }
    else { full.onload = swap; }
  }

  function toggleZoom() {
    lb.zoom = !lb.zoom;
    var img = lb.el.querySelector("[data-lb-img]");
    img.dataset.zoomed = lb.zoom ? "true" : "false";
    img.style.cursor = lb.zoom ? "zoom-out" : "zoom-in";
    /* 容器同步驱动 CSS 放大模式(stage 可滚动平移);取消放大时回到顶部 */
    lb.el.dataset.zoom = lb.zoom ? "true" : "false";
    /* 放大才需要真原图 1:1;fit 显示用高清版已足够,不必提前拉 10–25MB */
    if (lb.zoom) upgradeOriginal(lb.photos[lb.index], img);
    if (!lb.zoom) {
      var st = lb.el.querySelector(".lightbox__stage");
      st.scrollTop = 0;
      st.scrollLeft = 0;
    }
  }

  function paint() {
    var el = lb.el;
    if (!el) return;
    var p = lb.photos[lb.index];
    if (!p) return;
    var img = el.querySelector("[data-lb-img]");
    img.dataset.ready = "false";
    img.dataset.zoomed = "false";
    img.dataset.full = "false"; /* 切图后重新升级高清版 */
    lb.hi = false;              /* 切图后真原图需重新按需加载 */
    el.dataset.zoom = "false"; /* 切图/重开时退出放大模式(容器+图同步复位) */
    img.style.cursor = "zoom-in";

    /* 预取相邻两张(环形):首次浏览时提前进缓存,后续切换近瞬时 */
    [1, -1].forEach(function (d) {
      var q = lb.photos[(lb.index + d + lb.photos.length) % lb.photos.length];
      if (q) { var pre = new Image(); pre.src = lightboxSrc(q, 1800); }
    });

    /* fit 显示先用 1800w 预览图秒显(24MP 原图全尺寸解码是切图卡顿根源);
       随后自动后台升级 ≤2400w 高清版——点开即高清,无需任何操作。
       过期响应丢弃(已切走则不上屏) */
    var view = new Image();
    view.src = lightboxSrc(p, 1800);
    view.onload = function () {
      if (lb.photos[lb.index] !== p) return;
      img.src = view.src;
      img.alt = lb.title ? t("{title} — photo {n}", { title: lb.title, n: lb.index + 1 }) : t("Photo {n}", { n: lb.index + 1 });
      img.dataset.ready = "true";
      upgradeFull(p, img); /* 预览上屏后立即升级高清版 */
    };

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
    bindChrome();
    fav.bind();
    syncAll();
    bindPhotoTiles();
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
        fav.bind();
        syncAll();
        bindPhotoTiles();
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
    revealImages: revealImages,
    escapeHtml: escapeHtml,
    state: state
  };
})();
