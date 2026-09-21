/* ==========================================================================
   Photo Collection — shared runtime
   Chrome (header / drawer / search / footer / lightbox) is rendered from here
   so every page stays in sync. Page bodies are static HTML.
   ========================================================================== */

window.PC = (function () {
  var A = window.ARCHIVE;

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
    folder: '<path d="M3 6.5h6l1.8 2H21V19H3z"/>',
    image: '<rect x="3.5" y="4.5" width="17" height="15"/><path d="M3.5 15l4.5-4 4 3.5 3-2.5 5 4.5"/>',
    arrowLeft: '<path d="M20 12H4m0 0l6-6m-6 6l6 6"/>'
  };

  function icon(name, cls) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' +
      (cls ? ' class="' + cls + '"' : '') + '>' + ICONS[name] + "</svg>";
  }

  /* ---------- store ------------------------------------------------------ */
  var KEY = "pc.archive.v1";
  var state = { theme: "dark", favs: { model: [], collection: [], photo: [] } };

  try {
    var raw = localStorage.getItem(KEY);
    if (raw) {
      var saved = JSON.parse(raw);
      if (saved.theme) state.theme = saved.theme;
      if (saved.favs) {
        ["model", "collection", "photo"].forEach(function (k) {
          if (Array.isArray(saved.favs[k])) state.favs[k] = saved.favs[k];
        });
      }
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      state.theme = "light";
    }
  } catch (e) { /* storage unavailable — run with defaults */ }

  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {}
  }

  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", state.theme === "dark" ? "#0c0d0f" : "#ffffff");
    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      var glyph = icon(state.theme === "dark" ? "sun" : "moon");
      /* a button that carries its own wording keeps it and swaps only the icon */
      var slot = b.querySelector("[data-theme-icon]");
      if (slot) slot.innerHTML = glyph;
      else b.innerHTML = glyph;
      b.setAttribute("aria-label", state.theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
    });
  }

  function toggleTheme() {
    state.theme = state.theme === "dark" ? "light" : "dark";
    persist();
    applyTheme();
    document.dispatchEvent(new CustomEvent("pc:theme"));
  }

  /* ---------- favourites ------------------------------------------------- */
  var fav = {
    has: function (type, id) { return state.favs[type].indexOf(id) > -1; },
    toggle: function (type, id) {
      var list = state.favs[type];
      var i = list.indexOf(id);
      var added = i === -1;
      if (added) list.push(id); else list.splice(i, 1);
      persist();
      document.dispatchEvent(new CustomEvent("pc:fav", { detail: { type: type, id: id, added: added } }));
      return added;
    },
    list: function (type) { return state.favs[type].slice(); },
    counts: function () {
      return { model: state.favs.model.length, collection: state.favs.collection.length, photo: state.favs.photo.length };
    },
    /* bind every [data-fav] button inside root.
       The id is read at click time: a lightbox button keeps its listener while
       its target photo changes as you move through the set. */
    bind: function (root) {
      (root || document).querySelectorAll("[data-fav]").forEach(function (btn) {
        if (btn.dataset.favBound) return;
        btn.dataset.favBound = "1";
        sync(btn, btn.dataset.fav, btn.dataset.favId);
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          var type = btn.dataset.fav;
          var id = btn.dataset.favId;
          if (!id) return;
          var added = fav.toggle(type, id);
          sync(btn, type, id);
          toast(added ? "Saved to favourites" : "Removed from favourites");
        });
      });
    }
  };

  function sync(btn, type, id) {
    var on = fav.has(type, id);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    var label = btn.querySelector("[data-fav-label]");
    if (label) label.textContent = on ? "Saved" : "Save";
    var sr = btn.querySelector(".sr");
    if (sr) sr.textContent = (on ? "Remove from" : "Add to") + " favourites";
  }

  function syncAll() {
    document.querySelectorAll("[data-fav]").forEach(function (btn) {
      sync(btn, btn.dataset.fav, btn.dataset.favId);
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

  /* ---------- media helpers ---------------------------------------------- */
  /* A frame with a known aspect ratio: reserves space so nothing reflows,
     serves a responsive srcset, and fades in once the bytes arrive. */
  function frame(photo, opts) {
    opts = opts || {};
    var w = opts.w || 900;
    var cls = opts.cls || "frame";
    var ar = photo.ar || "3/4";
    var r = A.ratio(ar);
    var crop = opts.crop || "entropy";
    var srcset = [0.5, 1, 1.6]
      .map(function (m) {
        var ww = Math.round(w * m);
        return A.src(photo.id, { w: ww, ar: r, crop: crop }) + " " + ww + "w";
      })
      .join(", ");
    return '<div class="' + cls + ' skeleton" style="aspect-ratio:' + ar + '">' +
      '<img src="' + A.src(photo.id, { w: w, ar: r, crop: crop }) + '"' +
      ' srcset="' + srcset + '"' +
      ' sizes="' + (opts.sizes || "(max-width: 760px) 50vw, 25vw") + '"' +
      ' alt="' + (opts.alt || "") + '"' +
      ' loading="' + (opts.eager ? "eager" : "lazy") + '" decoding="async">' +
      "</div>";
  }

  function favButton(type, id, opts) {
    opts = opts || {};
    return '<button class="fav' + (opts.cls ? " " + opts.cls : "") + '" type="button"' +
      ' data-fav="' + type + '" data-fav-id="' + id + '" aria-pressed="false"' +
      ' title="' + (opts.title || "Favourite") + '">' +
      icon("heart") +
      (opts.labelled ? '<span data-fav-label>Save</span>' : "") +
      '<span class="sr">Add to favourites</span></button>';
  }

  function collectionCard(c, opts) {
    opts = opts || {};
    var m = A.model(c.model);
    return '<article class="collection-card hoverable">' +
      '<div style="position:relative">' +
      frame(c.cover, { w: opts.w || 900, crop: "entropy", alt: c.title + " — cover", cls: "frame " + (opts.frameCls || "") }) +
      '<div class="card__fav reveal">' + favButton("collection", c.slug, { cls: "fav--on-image", title: "Favourite collection" }) + "</div>" +
      "</div>" +
      '<div class="card__caption">' +
      '<div class="card__caption-main">' +
      '<h3 class="card__title"><a href="collection.html?c=' + c.slug + '">' + c.title + "</a></h3>" +
      '<p class="card__sub"><a href="model.html?m=' + m.slug + '">' + m.name + "</a><span>" + c.photos.length + " photos</span></p>" +
      "</div></div>" +
      "</article>";
  }

  function modelCard(m, opts) {
    opts = opts || {};
    return '<article class="model-card hoverable">' +
      '<div style="position:relative">' +
      '<a href="model.html?m=' + m.slug + '" aria-label="' + m.name + '">' +
      frame({ id: m.avatar, ar: "3/4" }, { w: opts.w || 800, crop: "faces", alt: m.name }) +
      "</a>" +
      '<div class="card__fav reveal">' + favButton("model", m.slug, { cls: "fav--on-image", title: "Favourite model" }) + "</div>" +
      "</div>" +
      '<h3 class="model-card__name"><a href="model.html?m=' + m.slug + '">' + m.name + "</a></h3>" +
      '<p class="model-card__meta">' + m.count + " " + (m.count === 1 ? "collection" : "collections") + "</p>" +
      '<p class="model-card__tags">' + m.tags.join(", ") + "</p>" +
      "</article>";
  }

  function photoTile(photo, collectionSlug, index) {
    return '<div class="photo-tile">' +
      frame(photo, { w: 700, crop: "entropy", alt: "" }) +
      '<button class="photo-tile__hit" type="button" data-photo-index="' + index + '"' +
      ' data-photo-collection="' + collectionSlug + '"' +
      ' aria-label="Open photo ' + (index + 1) + ' full screen"></button>' +
      '<span class="photo-tile__idx" aria-hidden="true">' + String(index + 1).padStart(2, "0") + "</span>" +
      "</div>";
  }

  /* ---------- image reveal ---------------------------------------------- */
  /* Hand the placeholder over to the photograph once it has decoded. Runs
     again for anything injected after boot. */
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

  /* ---------- query params ----------------------------------------------- */
  function qs(name, fallback) {
    var v = new URLSearchParams(location.search).get(name);
    return v === null || v === "" ? fallback : v;
  }

  /* ---------- chrome ----------------------------------------------------- */
  var NAV = [
    { href: "discovery.html", label: "Discovery", key: "discovery" },
    { href: "models.html", label: "Models", key: "models" },
    { href: "collections.html", label: "Collections", key: "collections" }
  ];

  function renderChrome() {
    var page = document.body.dataset.page || "";

    var header = document.querySelector("[data-header]");
    if (header) {
      header.className = "header";
      header.innerHTML =
        '<div class="wrap header__inner">' +
        '<button class="icon-btn header__burger" type="button" data-drawer-open aria-label="Open menu">' + icon("menu") + "</button>" +
        '<a class="wordmark" href="discovery.html">Photo&nbsp;<em>Collection</em></a>' +
        '<nav class="nav" aria-label="Primary">' +
        NAV.map(function (n) {
          return '<a class="nav__link" href="' + n.href + '"' + (n.key === page ? ' aria-current="page"' : "") + ">" + n.label + "</a>";
        }).join("") +
        "</nav>" +
        '<div class="header__end">' +
        '<button class="icon-btn" type="button" data-search-open aria-label="Search the archive">' + icon("search") + "</button>" +
        '<a class="icon-btn" href="favorites.html" aria-label="Favourites">' + icon("heart") +
        '<span class="icon-btn__dot" data-fav-dot hidden></span></a>' +
        '<button class="icon-btn" type="button" data-theme-toggle aria-label="Switch theme"></button>' +
        '<a class="avatar-btn" href="profile.html" aria-label="Your profile"><img src="' +
        A.src(A.USER.avatar, { w: 120, ar: 1, crop: "faces" }) + '" alt=""></a>' +
        "</div></div>";
    }

    var drawer = document.querySelector("[data-drawer]");
    if (drawer) {
      drawer.innerHTML =
        '<div class="drawer__top">' +
        '<a class="wordmark" href="discovery.html">Photo&nbsp;<em>Collection</em></a>' +
        '<button class="icon-btn" type="button" data-drawer-close aria-label="Close menu">' + icon("close") + "</button>" +
        "</div>" +
        '<nav class="drawer__nav" aria-label="Mobile">' +
        NAV.concat([
          { href: "favorites.html", label: "Favourites", key: "favorites" },
          { href: "profile.html", label: "Profile", key: "profile" }
        ]).map(function (n) {
          return '<a class="drawer__link" href="' + n.href + '"' + (n.key === page ? ' aria-current="page"' : "") + ">" + n.label + "</a>";
        }).join("") +
        "</nav>" +
        '<div class="drawer__foot">' +
        '<button class="btn btn--ghost btn--sm" type="button" data-search-open>Search</button>' +
        '<button class="btn btn--ghost btn--sm" type="button" data-theme-toggle>' +
        '<span data-theme-icon></span><span>Theme</span></button>' +
        '<a class="btn btn--ghost btn--sm" href="index.html">Log out</a>' +
        "</div>";
    }

    var search = document.querySelector("[data-search]");
    if (search) {
      search.innerHTML =
        '<div class="search__bar"><div class="wrap search__bar-inner">' +
        icon("search") +
        '<input class="search__input" type="search" data-search-input placeholder="Search models, collections, tags" aria-label="Search">' +
        '<button class="icon-btn" type="button" data-search-close aria-label="Close search">' + icon("close") + "</button>" +
        "</div></div>" +
        '<div class="wrap search__body" data-search-results></div>';
    }

    var footer = document.querySelector("[data-footer]");
    if (footer) {
      footer.className = "footer";
      footer.innerHTML =
        '<div class="wrap">' +
        '<div class="footer__top">' +
        "<div>" +
        '<p class="footer__wordmark">Photo&nbsp;<em>Collection</em></p>' +
        '<p class="footer__blurb">A digital archive of editorial photography. ' +
        A.COLLECTIONS.length + " collections, " + A.MODELS.length + " models.</p>" +
        "</div>" +
        '<div><p class="footer__col-title">Browse</p>' +
        '<a class="footer__link" href="discovery.html">Discovery</a>' +
        '<a class="footer__link" href="models.html">Models</a>' +
        '<a class="footer__link" href="collections.html">Collections</a></div>' +
        '<div><p class="footer__col-title">Your archive</p>' +
        '<a class="footer__link" href="favorites.html">Favourites</a>' +
        '<a class="footer__link" href="profile.html">Profile</a>' +
        '<a class="footer__link" href="profile.html#settings">Settings</a></div>' +
        '<div><p class="footer__col-title">Tags</p>' +
        A.TAGS.slice(0, 4).map(function (t) {
          return '<a class="footer__link" href="collections.html?tag=' + encodeURIComponent(t.name) + '">' + t.name + "</a>";
        }).join("") +
        "</div></div>" +
        '<div class="footer__bottom">' +
        "<span>© 2026 Photo Collection</span>" +
        "<span>All photographs are licensed to the archive.</span>" +
        "</div></div>";
    }
  }

  /* ---------- search ---------------------------------------------------- */
  function searchIndex(q) {
    q = q.trim().toLowerCase();
    if (!q) return null;
    return {
      models: A.MODELS.filter(function (m) {
        return (m.name + " " + m.stage + " " + m.tags.join(" ") + " " + (m.agency || "")).toLowerCase().indexOf(q) > -1;
      }),
      collections: A.COLLECTIONS.filter(function (c) {
        return (c.title + " " + c.tags.join(" ") + " " + A.model(c.model).name).toLowerCase().indexOf(q) > -1;
      }),
      tags: A.TAGS.filter(function (t) { return t.name.toLowerCase().indexOf(q) > -1; })
    };
  }

  var searchSuggestions = ["Fashion", "Editorial", "Monochrome", "Yang Chenchen", "Outdoor", "Studio"];

  function renderSearchResults(q) {
    var box = document.querySelector("[data-search-results]");
    if (!box) return;
    var r = searchIndex(q);

    if (!r) {
      box.innerHTML =
        '<div class="search__group">' +
        '<p class="search__group-title">Try a tag</p>' +
        '<div class="chip-row">' +
        searchSuggestions.map(function (s) {
          return '<button class="chip" type="button" data-search-suggest="' + s + '">' + s + "</button>";
        }).join("") +
        "</div></div>";
      return;
    }

    var total = r.models.length + r.collections.length + r.tags.length;
    if (!total) {
      box.innerHTML =
        '<div class="state">' +
        '<h2 class="state__title">No results found.</h2>' +
        '<p class="state__text">Nothing in the archive matches “' + escapeHtml(q) + '”. ' +
        "Try a broader term, or browse by tag.</p>" +
        '<a class="btn btn--ghost" href="collections.html">Browse collections</a>' +
        "</div>";
      return;
    }

    var html = "";
    if (r.models.length) {
      html += '<div class="search__group"><p class="search__group-title">Models</p>' +
        r.models.map(function (m) {
          return '<a class="search-row" href="model.html?m=' + m.slug + '">' +
            '<img class="search-row__thumb" src="' + A.src(m.avatar, { w: 160, ar: 0.75, crop: "faces" }) + '" alt="" loading="lazy">' +
            '<span><span class="search-row__name">' + m.name + "</span>" +
            '<span class="search-row__meta">' + m.tags.join(", ") + "</span></span>" +
            '<span class="search-row__end">' + m.count + " collections</span></a>";
        }).join("") + "</div>";
    }
    if (r.collections.length) {
      html += '<div class="search__group"><p class="search__group-title">Collections</p>' +
        r.collections.map(function (c) {
          return '<a class="search-row" href="collection.html?c=' + c.slug + '">' +
            '<img class="search-row__thumb" src="' + A.src(c.cover.id, { w: 160, ar: 0.75 }) + '" alt="" loading="lazy">' +
            '<span><span class="search-row__name">' + c.title + "</span>" +
            '<span class="search-row__meta">' + A.model(c.model).name + " — " + c.photos.length + " photos</span></span>" +
            '<span class="search-row__end">' + c.date + "</span></a>";
        }).join("") + "</div>";
    }
    if (r.tags.length) {
      html += '<div class="search__group"><p class="search__group-title">Tags</p>' +
        r.tags.map(function (t) {
          return '<a class="search-row" href="collections.html?tag=' + encodeURIComponent(t.name) + '">' +
            '<span class="search-row__name">' + t.name + "</span>" +
            '<span class="search-row__end">' + t.collections + " collections · " + t.models + " models</span></a>";
        }).join("") + "</div>";
    }
    box.innerHTML = html;
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
    renderSearchResults("");
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
  var lb = { photos: [], index: 0, title: "", collection: "", zoom: false, el: null };

  function lightboxEl() {
    if (lb.el) return lb.el;
    var el = document.createElement("div");
    el.className = "lightbox";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "Photo viewer");
    el.innerHTML =
      '<div class="lightbox__bar">' +
      '<span class="lightbox__title" data-lb-title></span>' +
      '<div class="lightbox__bar-end">' +
      '<button class="icon-btn" type="button" data-lb-close aria-label="Close viewer">' + icon("close") + "</button>" +
      "</div></div>" +
      '<div class="lightbox__stage">' +
      '<button class="lightbox__nav lightbox__nav--prev" type="button" data-lb-prev aria-label="Previous photo">' + icon("left") + "</button>" +
      '<img class="lightbox__img" data-lb-img alt="">' +
      '<button class="lightbox__nav lightbox__nav--next" type="button" data-lb-next aria-label="Next photo">' + icon("right") + "</button>" +
      "</div>" +
      '<div class="lightbox__foot">' +
      '<span class="lightbox__counter" data-lb-counter></span>' +
      '<div class="lightbox__foot-actions">' +
      favButton("photo", "", { labelled: true, title: "Favourite photo" }) +
      '<button class="btn btn--ghost btn--sm" type="button" data-lb-download>' + icon("download") + "<span>Download</span></button>" +
      "</div></div>" +
      '<div class="lightbox__progress"><i data-lb-progress></i></div>';
    document.body.appendChild(el);
    lb.el = el;

    el.querySelector("[data-lb-close]").addEventListener("click", close);
    el.querySelector("[data-lb-prev]").addEventListener("click", function () { go(-1); });
    el.querySelector("[data-lb-next]").addEventListener("click", function () { go(1); });
    el.querySelector("[data-lb-img]").addEventListener("click", toggleZoom);
    el.querySelector("[data-lb-download]").addEventListener("click", function (e) {
      simulateDownload(e.currentTarget, 1);
    });
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
    if (lb.returnFocus && document.contains(lb.returnFocus)) lb.returnFocus.focus();
  }

  function go(step) {
    if (!lb.photos.length) return;
    lb.index = (lb.index + step + lb.photos.length) % lb.photos.length;
    lb.zoom = false;
    paint();
  }

  function toggleZoom() {
    lb.zoom = !lb.zoom;
    var img = lb.el.querySelector("[data-lb-img]");
    img.dataset.zoomed = lb.zoom ? "true" : "false";
    img.style.cursor = lb.zoom ? "zoom-out" : "zoom-in";
    if (lb.zoom) {
      var p = lb.photos[lb.index];
      img.src = A.src(p.id, { w: 2400, ar: A.ratio(p.ar), crop: "entropy", q: 82 });
    } else {
      paint();
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
    img.style.cursor = "zoom-in";
    var next = new Image();
    next.src = A.src(p.id, { w: 1800, ar: A.ratio(p.ar), crop: "entropy", q: 78 });
    next.onload = function () {
      img.src = next.src;
      img.alt = lb.title ? lb.title + " — photo " + (lb.index + 1) : "Photo " + (lb.index + 1);
      img.dataset.ready = "true";
    };

    var title = el.querySelector("[data-lb-title]");
    title.textContent = lb.title || "";
    el.querySelector("[data-lb-counter]").textContent =
      String(lb.index + 1).padStart(2, "0") + " / " + String(lb.photos.length).padStart(2, "0");
    el.querySelector("[data-lb-progress]").style.width =
      ((lb.index + 1) / lb.photos.length) * 100 + "%";
    el.querySelector("[data-lb-prev]").disabled = lb.photos.length < 2;
    el.querySelector("[data-lb-next]").disabled = lb.photos.length < 2;

    /* the id changes as you move through the set, so bind once and read the
       id at click time rather than capturing it */
    var fb = el.querySelector("[data-fav]");
    fb.dataset.fav = "photo";
    fb.dataset.favId = lb.collection + ":" + lb.index;
    fav.bind(el);
    sync(fb, "photo", fb.dataset.favId);
  }

  /* ---------- download simulation --------------------------------------- */
  function simulateDownload(btn, fileCount) {
    if (btn.dataset.busy === "1") return;
    btn.dataset.busy = "1";
    var host = btn.closest("[data-download-host]") || btn.parentElement;
    var status = host.querySelector("[data-download-status]");
    var original = btn.innerHTML;

    if (!status) {
      btn.innerHTML = "Preparing…";
      setTimeout(function () {
        btn.innerHTML = original;
        btn.dataset.busy = "0";
        toast(fileCount > 1 ? "ZIP ready — " + fileCount + " photos" : "Download started");
      }, 1600);
      return;
    }

    btn.disabled = true;
    status.hidden = false;
    var fill = status.querySelector("[data-download-fill]");
    var label = status.querySelector("[data-download-label]");
    var pct = 0;
    label.textContent = "Preparing…";

    var t = setInterval(function () {
      pct += 4 + Math.random() * 9;
      if (pct >= 100) {
        pct = 100;
        clearInterval(t);
        fill.style.width = "100%";
        label.textContent = "ZIP ready";
        setTimeout(function () {
          status.hidden = true;
          fill.style.width = "0";
          btn.disabled = false;
          btn.dataset.busy = "0";
          toast("ZIP ready — " + fileCount + " photos");
        }, 900);
      } else {
        fill.style.width = pct + "%";
        label.textContent = "Preparing " + Math.round(pct) + "%";
      }
    }, 120);
  }

  /* ---------- masonry binding ------------------------------------------- */
  function bindPhotoTiles(root) {
    (root || document).querySelectorAll("[data-photo-index]").forEach(function (tile) {
      tile.addEventListener("click", function () {
        var slug = tile.dataset.photoCollection;
        var c = A.collection(slug);
        lb.returnFocus = tile;
        open({ photos: c.photos, index: Number(tile.dataset.photoIndex), title: c.title + " — " + A.model(c.model).name, collection: slug });
      });
    });
  }

  /* ---------- chrome events --------------------------------------------- */
  function bindChrome() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest("[data-theme-toggle]")) { toggleTheme(); return; }
      if (t.closest("[data-search-open]")) { closeDrawer(); openSearch(); return; }
      if (t.closest("[data-search-close]")) { closeSearch(); return; }
      if (t.closest("[data-drawer-open]")) { openDrawer(); return; }
      if (t.closest("[data-drawer-close]")) { closeDrawer(); return; }
      var sug = t.closest("[data-search-suggest]");
      if (sug) {
        var input = document.querySelector("[data-search-input]");
        input.value = sug.dataset.searchSuggest;
        renderSearchResults(input.value);
        input.focus();
        return;
      }
      if (t.closest("[data-download-all]")) {
        var all = t.closest("[data-download-all]");
        /* the collection page owns the frames, so count them from the wall */
        var n = document.querySelectorAll("[data-photo-index]").length;
        simulateDownload(all, n);
        return;
      }
      var single = t.closest("[data-download-single]");
      if (single) { simulateDownload(single, 1); return; }
    });

    document.addEventListener("input", function (e) {
      if (e.target.matches("[data-search-input]")) renderSearchResults(e.target.value);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { closeSearch(); closeDrawer(); }
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openSearch(); }
    });

    document.addEventListener("pc:fav", function (e) {
      document.querySelectorAll('[data-fav="' + e.detail.type + '"][data-fav-id="' + e.detail.id + '"]')
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
    if (window.PAGE_INIT) window.PAGE_INIT();
    bindPhotoTiles();
    fav.bind();
    syncAll();
    revealImages();
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
      });
    });
    mo.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  return {
    icon: icon,
    frame: frame,
    favButton: favButton,
    collectionCard: collectionCard,
    modelCard: modelCard,
    photoTile: photoTile,
    qs: qs,
    toast: toast,
    fav: fav,
    lightbox: { open: open, close: close },
    bindPhotoTiles: bindPhotoTiles,
    revealImages: revealImages,
    simulateDownload: simulateDownload,
    escapeHtml: escapeHtml,
    state: state
  };
})();
