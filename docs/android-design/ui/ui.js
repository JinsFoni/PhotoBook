/* ============================================================
   Photo Collection Android — 页面共享片段(JS 注入)
   状态栏 / 底栏 SVG 图标 / 主题切换 / 设计说明渲染
   ============================================================ */

const ICONS = {
  back: '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M15 5l-7 7 7 7"/></svg>',
  close: '<svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  search: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>',
  sort: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 7h16M7 12h10M10 17h4"/></svg>',
  heart: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M12 21s-7.5-4.7-10-9.3C.5 8 2.5 4.5 6 4.5c2.2 0 3.7 1.2 4.6 2.6L12 9l1.4-1.9c.9-1.4 2.4-2.6 4.6-2.6 3.5 0 5.5 3.5 4 7.2C19.5 16.3 12 21 12 21z"/></svg>',
  heartFill: '<svg width="20" height="20" viewBox="0 0 24 24" fill="#e0455a" stroke="#e0455a" stroke-width="1.7"><path d="M12 21s-7.5-4.7-10-9.3C.5 8 2.5 4.5 6 4.5c2.2 0 3.7 1.2 4.6 2.6L12 9l1.4-1.9c.9-1.4 2.4-2.6 4.6-2.6 3.5 0 5.5 3.5 4 7.2C19.5 16.3 12 21 12 21z"/></svg>',
  download: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14"/></svg>',
  copy: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="8" y="8" width="12" height="12" rx="1.5"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/></svg>',
  settings: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="3.2"/><path d="M5 12H3m18 0h-2M12 5V3m0 18v-2"/></svg>',
  tabExplore: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9h13v-9"/></svg>',
  tabCollections: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3.5" y="4" width="7" height="10.5" rx="1"/><rect x="13.5" y="4" width="7" height="10.5" rx="1"/><path d="M6 18.5h12"/></svg>',
  tabModels: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="8" r="3.6"/><path d="M5 20c1-3.8 3.8-5.6 7-5.6s6 1.8 7 5.6"/></svg>',
  tabFavorites: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 21s-7.5-4.7-10-9.3C.5 8 2.5 4.5 6 4.5c2.2 0 3.7 1.2 4.6 2.6L12 9l1.4-1.9c.9-1.4 2.4-2.6 4.6-2.6 3.5 0 5.5 3.5 4 7.2C19.5 16.3 12 21 12 21z"/></svg>',
};

const NAV_ORDER = ['explore', 'collections', 'models', 'favorites'];
const NAV_LABEL = { explore:'发现', collections:'写真', models:'模特', favorites:'收藏' };

/* 顶部页栏 */
function renderPagebar(active) {
  const el = document.getElementById('pagebar');
  if (!el) return;
  const prev = PAGES[(PAGES.indexOf(active) - 1 + PAGES.length) % PAGES.length];
  const next = PAGES[(PAGES.indexOf(active) + 1) % PAGES.length];
  const meta = PAGE_META[active];
  el.innerHTML = `
    <div class="pb-left"><a href="index.html">← 总览</a></div>
    <div class="pb-title">${meta.no} · ${meta.name}<span class="pb-tag">${meta.theme}</span></div>
    <div class="pb-right">
      <a class="pb-nav" href="${prev}.html">← ${PAGE_META[prev].name}</a>
      <a class="pb-nav" href="${next}.html">${PAGE_META[next].name} →</a>
      <button class="theme-btn" onclick="toggleTheme()">切换主题</button>
    </div>`;
}

/* 底栏 */
function renderTabbar(activeTab) {
  return `<div class="tabbar">` + NAV_ORDER.map(n => `
    <div class="tab ${n === activeTab ? 'active' : ''}">
      ${ICONS['tab' + n[0].toUpperCase() + n.slice(1)]}
      <span>${NAV_LABEL[n]}</span>
    </div>`).join('') + `</div>`;
}

/* 状态栏 */
function renderStatusbar() {
  return `<div class="statusbar">
    <span>9:41</span>
    <span class="sb-icons">
      <svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor"><rect x="0" y="7" width="2.6" height="4" rx="0.6"/><rect x="4.2" y="4.8" width="2.6" height="6.2" rx="0.6"/><rect x="8.4" y="2.4" width="2.6" height="8.6" rx="0.6"/><rect x="12.6" y="0" width="2.6" height="11" rx="0.6"/></svg>
      <svg width="23" height="11" viewBox="0 0 25 12" fill="none" stroke="currentColor"><rect x="1" y="1" width="20" height="10" rx="3"/><rect x="3" y="3" width="14" height="6" rx="1.5" fill="currentColor" stroke="none"/><path d="M23 4v4" stroke-linecap="round"/></svg>
    </span>
  </div>`;
}

/* 主题切换(三态循环:浅色→深色→虚化,与 Web 端一致;URL 参数保持) */
const THEMES = ['light', 'dark', 'blur'];
const THEME_LABEL = { light:'☾ 深色', dark:'✦ 虚化', blur:'☀ 浅色' };
const THEME_TAG = { light:'Light', dark:'Dark', blur:'Blur 虚化' };

function currentTheme() {
  const screen = document.querySelector('.screen');
  for (const t of THEMES) if (screen.classList.contains(t)) return t;
  return 'light';
}
function applyThemeFromURL() {
  const t = new URLSearchParams(location.search).get('t');
  const screen = document.querySelector('.screen');
  if (!screen) return;
  if (t && THEMES.includes(t)) {
    screen.classList.remove('light', 'dark', 'blur');
    screen.classList.add(t);
  }
  const btn = document.querySelector('.theme-btn');
  if (btn) btn.textContent = THEME_LABEL[currentTheme()];
  const tag = document.querySelector('.pb-tag');
  if (tag) tag.textContent = THEME_TAG[currentTheme()];
}
function toggleTheme() {
  const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
  const url = new URL(location);
  url.searchParams.set('t', next);
  location.href = url;
}

/* 设计说明侧栏 */
function renderNotes(items, spec) {
  const el = document.getElementById('notes');
  if (!el) return;
  const lis = Array.isArray(items) ? items.map(i => `<li>${i}</li>`).join('')
    : `<li>${items}</li>`;
  el.innerHTML = `<h3>设计说明</h3><ul>${lis}` +
    `</ul><div class="spec">` +
    (Array.isArray(spec) ? spec : Object.entries(spec)).map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('') +
    `</div>`;
}

/* 自动装配 */
document.addEventListener('DOMContentLoaded', () => {
  if (typeof PAGE_ID !== 'undefined' && PAGE_META[PAGE_ID]) renderPagebar(PAGE_ID);
  applyThemeFromURL();
  const sb = document.getElementById('statusbar-slot');
  if (sb) {
    const html = renderStatusbar();
    // 沉浸式:内容顶到屏幕顶的页面,状态栏白字叠加;否则透明悬浮于 paper 之上
    if (sb.classList.contains('overlay-on-media')) {
      sb.outerHTML = html.replace('class="statusbar"', 'class="statusbar overlay-on-media"');
    } else {
      sb.outerHTML = html;
    }
  }
  const tb = document.getElementById('tabbar-slot');
  if (tb) tb.outerHTML = renderTabbar(tb.dataset.tab);
  if (typeof NOTES !== 'undefined' && typeof SPEC !== 'undefined' && PAGE_META[PAGE_ID]) {
    renderNotes(NOTES[PAGE_ID] || [], SPEC[PAGE_ID] || []);
  }
});
