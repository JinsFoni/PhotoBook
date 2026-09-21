"""i18n — 简体中文(zh-CN)与繁体中文(zh-TW)双语言支持。

设计:
- 不用 gettext;单文件字典 STRINGS:msgid → {语言: 译文}。
- msgid 一律取英文原文(前台原有文案);Python 侧原有中文消息也统一
  收录为 msgid(键即中文原文,zh-CN/zh-TW 各给译文),调用处零改动。
- 当前语言保存在 ContextVar,由 main.py 中间件在请求早期设置;
  模板经 Jinja 全局 t()/lang() 读取,JS 经 boot_json 的 i18n 字段读取。
- 回退链:请求语言 → zh-CN 条目 → msgid 原文(英文)。

约定(词汇表):
- Models 模特/模特兒;Collections 写真集/寫真集;Favourites 收藏;
  Save(收藏按钮)收藏;表单保存 保存/儲存;archive 档案馆/檔案館。
- 品牌 "Photo Collection" 不翻译;角色 user/admin 与 harvest 状态码保留原文。
"""

from __future__ import annotations

from contextvars import ContextVar

DEFAULT_LANG = "zh-CN"

# 语言代码 → 显示名(语言切换器用,显示名永远用自身语言书写)
LANGUAGES: dict[str, str] = {
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
}

_lang_var: ContextVar[str] = ContextVar("pb_lang", default=DEFAULT_LANG)


def set_language(code: str) -> None:
    _lang_var.set(code if code in LANGUAGES else DEFAULT_LANG)


def get_language() -> str:
    return _lang_var.get()


def normalize_lang(raw: str | None) -> str | None:
    """宽松归一语言代码:zh-tw/zh-hant/zh-hk → zh-TW;zh/zh-cn/zh-hans → zh-CN。"""
    if not raw:
        return None
    v = raw.strip().replace("_", "-").lower()
    if not v:
        return None
    if v in ("zh-tw", "zh-hant", "zh-hk", "zh-hant-tw", "zh-hk-hant"):
        return "zh-TW"
    if v in ("zh", "zh-cn", "zh-hans", "zh-sg", "zh-hans-cn", "cmn"):
        return "zh-CN"
    return None


def translate(msgid: str, lang: str | None = None, **kw) -> str:
    """取译文;无条目或无该语言时回退 zh-CN,再回退 msgid 原文。占位符 {x} 替换。"""
    code = lang or get_language()
    entry = STRINGS.get(msgid)
    out: str | None = None
    if entry:
        out = entry.get(code) or entry.get("zh-CN")
    if out is None:
        out = msgid
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def tf(msgid: str, *args) -> str:
    """按位置插值 {1} {2} …(Python 侧便捷)。"""
    out = translate(msgid)
    for i, v in enumerate(args, 1):
        out = out.replace("{" + str(i) + "}", str(v))
    return out


# 路由/模板常用短别名
t = translate


# ============================================================================
# 翻译表。msgid = 英文原文(或既有中文消息原文);缺 zh-CN 条目即回退原文。
# ============================================================================

STRINGS: dict[str, dict[str, str]] = {
    # ---- chrome(app.js:导航/页脚/抽屉)------------------------------------
    "Discovery": {"zh-CN": "发现", "zh-TW": "發現"},
    "Model": {"zh-CN": "模特", "zh-TW": "模特兒"},
    "Name": {"zh-CN": "名字", "zh-TW": "名字"},
    "Edit": {"zh-CN": "编辑", "zh-TW": "編輯"},
    "New": {"zh-CN": "新建", "zh-TW": "新增"},
    "Age": {"zh-CN": "年龄", "zh-TW": "年齡"},
    "Photos": {"zh-CN": "照片", "zh-TW": "照片"},
    "{n} active": {"zh-CN": "{n} 个活动", "zh-TW": "{n} 個活動"},
    "Models": {"zh-CN": "模特", "zh-TW": "模特兒"},
    "Collections": {"zh-CN": "写真集", "zh-TW": "寫真集"},
    "Favourites": {"zh-CN": "收藏", "zh-TW": "收藏"},
    "Profile": {"zh-CN": "个人中心", "zh-TW": "個人中心"},
    "Settings": {"zh-CN": "设置", "zh-TW": "設定"},
    "Admin Dashboard": {"zh-CN": "管理后台", "zh-TW": "管理後台"},
    "Log out": {"zh-CN": "退出登录", "zh-TW": "登出"},
    "Search": {"zh-CN": "搜索", "zh-TW": "搜尋"},
    "Theme": {"zh-CN": "主题", "zh-TW": "主題"},
    "Browse": {"zh-CN": "浏览", "zh-TW": "瀏覽"},
    "Tags": {"zh-CN": "标签", "zh-TW": "標籤"},
    "Your archive": {"zh-CN": "我的档案馆", "zh-TW": "我的檔案館"},
    "Open menu": {"zh-CN": "打开菜单", "zh-TW": "開啟選單"},
    "Close menu": {"zh-CN": "关闭菜单", "zh-TW": "關閉選單"},
    "Primary": {"zh-CN": "主导航", "zh-TW": "主導覽"},
    "Mobile": {"zh-CN": "移动端导航", "zh-TW": "行動版導覽"},
    "Search the archive": {"zh-CN": "搜索档案馆", "zh-TW": "搜尋檔案館"},
    "Favourites page": {"zh-CN": "收藏页", "zh-TW": "收藏頁"},
    "Your profile": {"zh-CN": "个人中心", "zh-TW": "個人中心"},
    "Skip to content": {"zh-CN": "跳到主要内容", "zh-TW": "跳至主要內容"},
    "A digital archive of editorial photography. {c} collections, {m} models.": {
        "zh-CN": "一本编辑摄影的数字档案馆。{c} 个写真集,{m} 位模特。",
        "zh-TW": "一本時尚攝影的數位檔案館。{c} 個寫真集,{m} 位模特兒。"},
    "All photographs are licensed to the archive.": {
        "zh-CN": "所有照片均授权收录于档案馆。",
        "zh-TW": "所有照片均授權收錄於檔案館。"},

    # ---- 主题(app.js / profile)-------------------------------------------
    "Switch to light theme": {"zh-CN": "切换到浅色主题", "zh-TW": "切換至淺色主題"},
    "Switch to dark theme": {"zh-CN": "切换到深色主题", "zh-TW": "切換至深色主題"},
    "Switch theme": {"zh-CN": "切换主题", "zh-TW": "切換主題"},
    "Dark theme": {"zh-CN": "深色主题", "zh-TW": "深色主題"},
    "Gallery (dark)": {"zh-CN": "画廊(深色)", "zh-TW": "藝廊(深色)"},
    "Editorial (light)": {"zh-CN": "素雅(浅色)", "zh-TW": "素雅(淺色)"},

    # ---- 搜索(app.js)------------------------------------------------------
    "Search models, collections, tags": {
        "zh-CN": "搜索模特、写真集、标签",
        "zh-TW": "搜尋模特兒、寫真集、標籤"},
    "Close search": {"zh-CN": "关闭搜索", "zh-TW": "關閉搜尋"},
    "Try a tag": {"zh-CN": "试试这些标签", "zh-TW": "試試這些標籤"},
    "No results found.": {"zh-CN": "没有找到结果。", "zh-TW": "沒有找到結果。"},
    "Nothing in the archive matches “{q}”. Try a broader term, or browse by tag.": {
        "zh-CN": "档案馆里没有与“{q}”匹配的内容。换个更宽泛的词,或按标签浏览。",
        "zh-TW": "檔案館裡沒有與「{q}」相符的內容。換個更寬鬆的詞,或依標籤瀏覽。"},
    "Browse collections": {"zh-CN": "浏览写真集", "zh-TW": "瀏覽寫真集"},

    # ---- 收藏(app.js / _ui)------------------------------------------------
    "Save": {"zh-CN": "收藏", "zh-TW": "收藏"},
    "Saved": {"zh-CN": "已收藏", "zh-TW": "已收藏"},
    "Save failed — please retry": {"zh-CN": "收藏失败,请重试", "zh-TW": "收藏失敗,請重試"},
    "Saved to favourites": {"zh-CN": "已加入收藏", "zh-TW": "已加入收藏"},
    "Removed from favourites": {"zh-CN": "已取消收藏", "zh-TW": "已取消收藏"},
    "Add to favourites": {"zh-CN": "加入收藏", "zh-TW": "加入收藏"},
    "Remove from favourites": {"zh-CN": "移出收藏", "zh-TW": "移出收藏"},
    "Favourite": {"zh-CN": "收藏", "zh-TW": "收藏"},
    "Favourite model": {"zh-CN": "收藏模特", "zh-TW": "收藏模特兒"},
    "Favourite collection": {"zh-CN": "收藏写真集", "zh-TW": "收藏寫真集"},
    "Favourite photo": {"zh-CN": "收藏照片", "zh-TW": "收藏照片"},

    # ---- 灯箱(app.js)------------------------------------------------------
    "Photo viewer": {"zh-CN": "照片查看器", "zh-TW": "照片檢視器"},
    "Close viewer": {"zh-CN": "关闭查看器", "zh-TW": "關閉檢視器"},
    "Previous photo": {"zh-CN": "上一张", "zh-TW": "上一張"},
    "Next photo": {"zh-CN": "下一张", "zh-TW": "下一張"},
    "Download": {"zh-CN": "下载", "zh-TW": "下載"},
    "{title} — photo {n}": {"zh-CN": "{title} — 第 {n} 张", "zh-TW": "{title} — 第 {n} 張"},
    "Photo {n}": {"zh-CN": "第 {n} 张", "zh-TW": "第 {n} 張"},
    "Archive export is coming soon": {"zh-CN": "打包下载即将上线", "zh-TW": "打包下載即將上線"},

    # ---- 数量词(计数)-------------------------------------------------------
    "collection": {"zh-CN": "个写真集", "zh-TW": "個寫真集"},
    "collections": {"zh-CN": "个写真集", "zh-TW": "個寫真集"},
    "model": {"zh-CN": "位模特", "zh-TW": "位模特兒"},
    "models": {"zh-CN": "位模特", "zh-TW": "位模特兒"},
    "photos": {"zh-CN": "张照片", "zh-TW": "張照片"},
    "frames": {"zh-CN": "帧", "zh-TW": "幀"},
    "tags": {"zh-CN": "个标签", "zh-TW": "個標籤"},
    "{n} photos": {"zh-CN": "{n} 张照片", "zh-TW": "{n} 張照片"},
    "{n} photos · {m}": {"zh-CN": "{n} 张照片 · {m}", "zh-TW": "{n} 張照片 · {m}"},
    "{n} collection": {"zh-CN": "{n} 个写真集", "zh-TW": "{n} 個寫真集"},
    "{n} collections": {"zh-CN": "{n} 个写真集", "zh-TW": "{n} 個寫真集"},
    "{n} model": {"zh-CN": "{n} 位模特", "zh-TW": "{n} 位模特兒"},
    "{n} models": {"zh-CN": "{n} 位模特", "zh-TW": "{n} 位模特兒"},
    "{n} frames": {"zh-CN": "{n} 帧", "zh-TW": "{n} 幀"},
    "{n} tags": {"zh-CN": "{n} 个标签", "zh-TW": "{n} 個標籤"},
    "{n} collections · {m} models": {
        "zh-CN": "{n} 个写真集 · {m} 位模特",
        "zh-TW": "{n} 個寫真集 · {m} 位模特兒"},
    "{n} collections · {m} photos": {
        "zh-CN": "{n} 个写真集 · {m} 张照片",
        "zh-TW": "{n} 個寫真集 · {m} 張照片"},

    # ---- Discovery 页 -------------------------------------------------------
    "Featured collection": {"zh-CN": "本期精选写真集", "zh-TW": "本期精選寫真集"},
    "View collection": {"zh-CN": "进入写真集", "zh-TW": "進入寫真集"},
    "Contact sheet": {"zh-CN": "缩略样张", "zh-TW": "縮圖樣張"},
    "Featured {i} / {n}": {"zh-CN": "精选 {i} / {n}", "zh-TW": "精選 {i} / {n}"},
    "Select a frame to preview it above": {
        "zh-CN": "点选一张样张即可在上方预览",
        "zh-TW": "點選一張樣張即可在上方預覽"},
    "Previous set": {"zh-CN": "上一组", "zh-TW": "上一組"},
    "Next set": {"zh-CN": "下一组", "zh-TW": "下一組"},
    "Frames in the featured collection": {
        "zh-CN": "本期精选的样张", "zh-TW": "本期精選的樣張"},
    "Preview frame {i} of {title}": {
        "zh-CN": "预览《{title}》第 {i} 张",
        "zh-TW": "預覽《{title}》第 {i} 張"},
    "Latest Collections": {"zh-CN": "最新写真集", "zh-TW": "最新寫真集"},
    "All collections": {"zh-CN": "全部写真集", "zh-TW": "全部寫真集"},
    "Featured Models": {"zh-CN": "精选模特", "zh-TW": "精選模特兒"},
    "All models": {"zh-CN": "全部模特", "zh-TW": "全部模特兒"},
    "Explore": {"zh-CN": "探索", "zh-TW": "探索"},
    "Browse Models": {"zh-CN": "浏览模特", "zh-TW": "瀏覽模特兒"},
    "Editorial and portrait profiles": {
        "zh-CN": "人像与写真档案", "zh-TW": "人像與寫真檔案"},
    "Browse Collections": {"zh-CN": "浏览写真集", "zh-TW": "瀏覽寫真集"},
    "Every published sitting": {"zh-CN": "所有已发布的写真", "zh-TW": "所有已發佈的寫真"},
    "Browse Tags": {"zh-CN": "浏览标签", "zh-TW": "瀏覽標籤"},
    "Start from a theme": {"zh-CN": "从一个主题开始", "zh-TW": "從一個主題開始"},
    "Browse by tag": {"zh-CN": "按标签浏览", "zh-TW": "依標籤瀏覽"},

    # ---- Models 页 ----------------------------------------------------------
    "Models page": {"zh-CN": "模特", "zh-TW": "模特兒"},
    "Profiles in the archive. Each one collects the sittings we have published with that model.": {
        "zh-CN": "档案馆中的模特档案。每份档案收录该模特已发布的全部写真。",
        "zh-TW": "檔案館中的模特兒檔案。每份檔案收錄該模特兒已發佈的全部寫真。"},
    "Search by name or stage name": {
        "zh-CN": "按名字或艺名搜索", "zh-TW": "按名字或藝名搜尋"},
    "Search models": {"zh-CN": "搜索模特", "zh-TW": "搜尋模特兒"},
    "Gender": {"zh-CN": "性别", "zh-TW": "性別"},
    "Any gender": {"zh-CN": "不限性别", "zh-TW": "不限性別"},
    "Female": {"zh-CN": "女", "zh-TW": "女"},
    "Male": {"zh-CN": "男", "zh-TW": "男"},
    "Tag": {"zh-CN": "标签", "zh-TW": "標籤"},
    "Any tag": {"zh-CN": "不限标签", "zh-TW": "不限標籤"},
    "Agency": {"zh-CN": "经纪公司", "zh-TW": "經紀公司"},
    "Any agency": {"zh-CN": "不限公司", "zh-TW": "不限公司"},
    "Sort": {"zh-CN": "排序", "zh-TW": "排序"},
    "Sort: Recommended": {"zh-CN": "排序:推荐", "zh-TW": "排序:推薦"},
    "Sort: Latest": {"zh-CN": "排序:最新", "zh-TW": "排序:最新"},
    "Sort: Name": {"zh-CN": "排序:名字", "zh-TW": "排序:名字"},
    "Sort: Newest": {"zh-CN": "排序:最新", "zh-TW": "排序:最新"},
    "Sort: Oldest": {"zh-CN": "排序:最早", "zh-TW": "排序:最早"},
    "Sort: Title": {"zh-CN": "排序:标题", "zh-TW": "排序:標題"},
    "Sort: Most photos": {"zh-CN": "排序:照片最多", "zh-TW": "排序:照片最多"},
    "Reset": {"zh-CN": "重置", "zh-TW": "重設"},
    "Clear filters": {"zh-CN": "清除筛选", "zh-TW": "清除篩選"},
    "No models match those filters.": {
        "zh-CN": "没有符合筛选条件的模特。", "zh-TW": "沒有符合篩選條件的模特兒。"},
    "Try removing a filter, or search a different name.": {
        "zh-CN": "试试去掉一个筛选条件,或换个名字搜索。",
        "zh-TW": "試試去掉一個篩選條件,或換個名字搜尋。"},

    # ---- Collections 页 -----------------------------------------------------
    "Every published sitting in the archive, newest first.": {
        "zh-CN": "档案馆中所有已发布的写真,按时间从新到旧。",
        "zh-TW": "檔案館中所有已發佈的寫真,按時間從新到舊。"},
    "Search titles and models": {"zh-CN": "搜索标题与模特", "zh-TW": "搜尋標題與模特兒"},
    "Search collections": {"zh-CN": "搜索写真集", "zh-TW": "搜尋寫真集"},
    "Any model": {"zh-CN": "不限模特", "zh-TW": "不限模特兒"},
    "No collections match those filters.": {
        "zh-CN": "没有符合筛选条件的写真集。", "zh-TW": "沒有符合篩選條件的寫真集。"},
    "Try a different tag, or clear the filters to see the whole archive.": {
        "zh-CN": "换个标签试试,或清除筛选查看全部档案馆。",
        "zh-TW": "換個標籤試試,或清除篩選查看全部檔案館。"},
    "Load more collections": {"zh-CN": "加载更多写真集", "zh-TW": "載入更多寫真集"},
    "Load more models": {"zh-CN": "加载更多模特", "zh-TW": "載入更多模特"},

    # ---- Collection 详情页 ---------------------------------------------------
    "Select any frame to open it full screen": {
        "zh-CN": "点选任意一张即可全屏查看",
        "zh-TW": "點選任意一張即可全螢幕檢視"},
    "No photos yet.": {"zh-CN": "还没有照片。", "zh-TW": "還沒有照片。"},
    "This collection has been created but the frames have not been uploaded.": {
        "zh-CN": "写真集已建立,但照片尚未上传。",
        "zh-TW": "寫真集已建立,但照片尚未上傳。"},
    "Back to collections": {"zh-CN": "返回写真集", "zh-TW": "返回寫真集"},
    "More from this archive": {"zh-CN": "档案馆中的更多内容", "zh-TW": "檔案館中的更多內容"},
    "More from {name}": {"zh-CN": "{name} 的更多写真", "zh-TW": "{name} 的更多寫真"},
    "Open photo {n} full screen": {
        "zh-CN": "全屏查看第 {n} 张照片",
        "zh-TW": "全螢幕檢視第 {n} 張照片"},

    # ---- Model 详情页 --------------------------------------------------------
    "About": {"zh-CN": "关于", "zh-TW": "關於"},
    "Known as {s}": {"zh-CN": "艺名 {s}", "zh-TW": "藝名 {s}"},
    "No collections yet.": {"zh-CN": "还没有写真集。", "zh-TW": "還沒有寫真集。"},
    "Nothing from this profile has been published.": {
        "zh-CN": "该档案暂无已发布的内容。",
        "zh-TW": "該檔案暫無已發佈的內容。"},
    "Browse the archive": {"zh-CN": "浏览档案馆", "zh-TW": "瀏覽檔案館"},
    "Height": {"zh-CN": "身高", "zh-TW": "身高"},
    "Measurements": {"zh-CN": "三围", "zh-TW": "三圍"},
    "In archive since": {"zh-CN": "入驻时间", "zh-TW": "入駐時間"},

    # ---- Favourites 页 --------------------------------------------------------
    "Everything you have kept. Models, collections and single frames, in one place.": {
        "zh-CN": "你收藏的一切——模特、写真集与单张照片,都在这里。",
        "zh-TW": "你收藏的一切——模特兒、寫真集與單張照片,都在這裡。"},
    "Favourite types": {"zh-CN": "收藏类型", "zh-TW": "收藏類型"},
    "Start browsing": {"zh-CN": "开始浏览", "zh-TW": "開始瀏覽"},
    "No favourites yet.": {"zh-CN": "还没有收藏。", "zh-TW": "還沒有收藏。"},
    "No favourite models yet.": {"zh-CN": "还没有收藏模特。", "zh-TW": "還沒有收藏模特兒。"},
    "Save a model from any profile or listing and their full archive will be waiting here.": {
        "zh-CN": "在模特档案或列表中点击收藏,她的全部写真都会汇集在这里。",
        "zh-TW": "在模特兒檔案或列表中點擊收藏,她的全部寫真都會彙集在這裡。"},
    "No favourite collections yet.": {
        "zh-CN": "还没有收藏写真集。", "zh-TW": "還沒有收藏寫真集。"},
    "Save a collection while you browse and it will appear here for quick access.": {
        "zh-CN": "浏览时收藏的写真集会出现在这里,方便随时回看。",
        "zh-TW": "瀏覽時收藏的寫真集會出現在這裡,方便隨時回看。"},
    "No favourite photos yet.": {"zh-CN": "还没有收藏照片。", "zh-TW": "還沒有收藏照片。"},
    "Open any frame full screen and save it — single frames you keep are collected here.": {
        "zh-CN": "全屏打开任意一张并收藏——你保留的单张照片都汇集在此。",
        "zh-TW": "全螢幕開啟任意一張並收藏——你保留的單張照片都彙集在此。"},

    # ---- Profile 页 -----------------------------------------------------------
    "Member of the archive": {"zh-CN": "档案馆成员", "zh-TW": "檔案館成員"},
    "View favourites": {"zh-CN": "查看收藏", "zh-TW": "查看收藏"},
    "Account": {"zh-CN": "账户", "zh-TW": "帳戶"},
    "Overview": {"zh-CN": "总览", "zh-TW": "總覽"},
    "Favourite models": {"zh-CN": "收藏的模特", "zh-TW": "收藏的模特兒"},
    "Favourite collections": {"zh-CN": "收藏的写真集", "zh-TW": "收藏的寫真集"},
    "Favourite photos": {"zh-CN": "收藏的照片", "zh-TW": "收藏的照片"},
    "Models saved": {"zh-CN": "位模特", "zh-TW": "位模特兒"},
    "Collections saved": {"zh-CN": "个写真集", "zh-TW": "個寫真集"},
    "Photos saved": {"zh-CN": "张照片", "zh-TW": "張照片"},
    "Recently saved": {"zh-CN": "最近收藏", "zh-TW": "最近收藏"},
    "All favourites": {"zh-CN": "全部收藏", "zh-TW": "全部收藏"},
    "Nothing saved yet.": {"zh-CN": "还没有收藏。", "zh-TW": "還沒有收藏。"},
    "Favourites you keep while browsing show up here.": {
        "zh-CN": "浏览时收藏的内容会显示在这里。",
        "zh-TW": "瀏覽時收藏的內容會顯示在這裡。"},
    "Appearance": {"zh-CN": "外观", "zh-TW": "外觀"},
    "The archive opens in Gallery (dark) by default. Editorial (light) keeps the interface quiet against white.": {
        "zh-CN": "档案馆默认以画廊(深色)打开。素雅(浅色)在白色背景下更安静。",
        "zh-TW": "檔案館預設以藝廊(深色)開啟。素雅(淺色)在白色背景下更安靜。"},
    "Language": {"zh-CN": "语言", "zh-TW": "語言"},
    "Interface language. Choice is saved to your account and takes effect at once.": {
        "zh-CN": "界面显示语言。选择会保存到账户并立即生效。",
        "zh-TW": "介面顯示語言。選擇會儲存到帳戶並立即生效。"},
    "Session": {"zh-CN": "会话", "zh-TW": "工作階段"},
    "Signed in as {u} ({r}).": {
        "zh-CN": "当前登录:{u}({r})。",
        "zh-TW": "目前登入:{u}({r})。"},

    # ---- Login 页 ---------------------------------------------------------------
    "Sign in": {"zh-CN": "登录", "zh-TW": "登入"},
    "Now showing": {"zh-CN": "正在展出", "zh-TW": "正在展出"},
    "Photo Archive": {"zh-CN": "照片档案馆", "zh-TW": "照片檔案館"},
    "Private archive": {"zh-CN": "私有档案馆", "zh-TW": "私有檔案館"},
    "Archive": {"zh-CN": "档案馆", "zh-TW": "檔案館"},
    "The archive is open to members. Sign in to browse models, collections and downloads.": {
        "zh-CN": "档案馆仅向成员开放。登录后即可浏览模特、写真集与下载。",
        "zh-TW": "檔案館僅向成員開放。登入後即可瀏覽模特兒、寫真集與下載。"},
    "Username": {"zh-CN": "用户名", "zh-TW": "使用者名稱"},
    "Password": {"zh-CN": "密码", "zh-TW": "密碼"},
    "Keep me signed in": {"zh-CN": "保持登录", "zh-TW": "保持登入"},
    "No account yet? Ask the archive administrator for access.": {
        "zh-CN": "还没有账号?请联系档案馆管理员开通。",
        "zh-TW": "還沒有帳號?請聯絡檔案館管理員開通。"},
    "用户名或密码不正确。": {
        "zh-CN": "用户名或密码不正确。",
        "zh-TW": "使用者名稱或密碼不正確。"},

    # ---- 404 页 -------------------------------------------------------------------
    "Not found — Photo Collection": {
        "zh-CN": "页面不存在 — Photo Collection",
        "zh-TW": "頁面不存在 — Photo Collection"},
    "Something went wrong.": {"zh-CN": "页面走丢了。", "zh-TW": "頁面走丟了。"},
    "We couldn't find that {w}. The link may be out of date.": {
        "zh-CN": "找不到这个{w},链接可能已经过期。",
        "zh-TW": "找不到這個{w},連結可能已經過期。"},
    "Back to discovery": {"zh-CN": "返回发现页", "zh-TW": "返回發現頁"},
    "page": {"zh-CN": "页面", "zh-TW": "頁面"},
    "写真": {"zh-CN": "写真集", "zh-TW": "寫真集"},
    
    # ---- Admin:导航与仪表盘 --------------------------------------------------------
    "Admin": {"zh-CN": "管理后台", "zh-TW": "管理後台"},
    "Dashboard": {"zh-CN": "仪表盘", "zh-TW": "儀表板"},
    "Harvest": {"zh-CN": "采集下载", "zh-TW": "採集下載"},
    "Users": {"zh-CN": "用户", "zh-TW": "使用者"},
    "← Back to site": {"zh-CN": "← 返回前台", "zh-TW": "← 返回前台"},
    "Archive management — content, users and the harvest pipeline.": {
        "zh-CN": "档案馆管理——内容、用户与采集管线。",
        "zh-TW": "檔案館管理——內容、使用者與採集管線。"},
    "Harvest queue": {"zh-CN": "采集队列", "zh-TW": "採集佇列"},
    "Harvested": {"zh-CN": "已采集", "zh-TW": "已採集"},
    "Failed": {"zh-CN": "失败", "zh-TW": "失敗"},
    "Worker": {"zh-CN": "执行器", "zh-TW": "執行器"},
    "Recent harvest jobs": {"zh-CN": "最近采集任务", "zh-TW": "最近採集任務"},
    "All jobs": {"zh-CN": "全部任务", "zh-TW": "全部任務"},
    "Serial": {"zh-CN": "序号", "zh-TW": "序號"},
    "Title": {"zh-CN": "标题", "zh-TW": "標題"},
    "Status": {"zh-CN": "状态", "zh-TW": "狀態"},
    "Time": {"zh-CN": "时间", "zh-TW": "時間"},
    "No jobs yet.": {"zh-CN": "还没有任务。", "zh-TW": "還沒有任務。"},
    "Run a scan or submit a URL on the 采集下载 page.": {
        "zh-CN": "在采集下载页提交链接或执行扫描即可开始。",
        "zh-TW": "在採集下載頁提交連結或執行掃描即可開始。"},
    "running": {"zh-CN": "运行中", "zh-TW": "執行中"},
    "stopped": {"zh-CN": "已停止", "zh-TW": "已停止"},

    # ---- Admin:采集下载页 -----------------------------------------------------------
    "从 buondua.com 抓取写真 → ouo 链接解析 → MediaFire 下载 → 7zz 解压归档。串行队列,一次一个。": {
        "zh-CN": "从 buondua.com 抓取写真 → ouo 链接解析 → MediaFire 下载 → 7zz 解压归档。串行队列,一次一个。",
        "zh-TW": "從 buondua.com 擷取寫真 → ouo 連結解析 → MediaFire 下載 → 7zz 解壓歸檔。序列佇列,一次一個。"},
    "手动提交": {"zh-CN": "手动提交", "zh-TW": "手動提交"},
    "粘贴写真详情页地址(buondua.com 域名),按序号自动去重。": {
        "zh-CN": "粘贴写真详情页地址(buondua.com 域名),按序号自动去重。",
        "zh-TW": "貼上寫真詳情頁地址(buondua.com 網域),按序號自動去重。"},
    "加入队列": {"zh-CN": "加入队列", "zh-TW": "加入佇列"},
    "扫描新写真": {"zh-CN": "扫描新写真", "zh-TW": "掃描新寫真"},
    "自动扫描列表页发现新条目(白/黑名单过滤)。定时任务 {on},每 {h}h,从第 {s} 页扫 {p} 页/轮。": {
        "zh-CN": "自动扫描列表页发现新条目(白/黑名单过滤)。定时任务{on},每 {h} 小时,从第 {s} 页扫 {p} 页/轮。",
        "zh-TW": "自動掃描列表頁發現新條目(白/黑名單過濾)。定時任務{on},每 {h} 小時,從第 {s} 頁掃 {p} 頁/輪。"},
    "开启": {"zh-CN": "开启", "zh-TW": "開啟"},
    "关闭": {"zh-CN": "关闭", "zh-TW": "關閉"},
    "立即扫描": {"zh-CN": "立即扫描", "zh-TW": "立即掃描"},
    "配置规则": {"zh-CN": "配置规则", "zh-TW": "設定規則"},
    "历史累计 {n} 条(永不重复处理)。": {
        "zh-CN": "历史累计 {n} 条(永不重复处理)。",
        "zh-TW": "歷史累計 {n} 條(永不重複處理)。"},
    "任务队列": {"zh-CN": "任务队列", "zh-TW": "任務佇列"},
    "{n} 个活动": {"zh-CN": "{n} 个活动", "zh-TW": "{n} 個活動"},
    "Worker 运行中": {"zh-CN": "Worker 运行中", "zh-TW": "Worker 執行中"},
    "Worker 已停止": {"zh-CN": "Worker 已停止", "zh-TW": "Worker 已停止"},
    "模特": {"zh-CN": "模特", "zh-TW": "模特兒"},
    "Serial": {"zh-CN": "序号", "zh-TW": "序號"},
    "标题": {"zh-CN": "标题", "zh-TW": "標題"},
    "状态": {"zh-CN": "状态", "zh-TW": "狀態"},
    "时间": {"zh-CN": "时间", "zh-TW": "時間"},
    "Role": {"zh-CN": "角色", "zh-TW": "角色"},
    "进度": {"zh-CN": "进度", "zh-TW": "進度"},
    "来源": {"zh-CN": "来源", "zh-TW": "來源"},
    "操作": {"zh-CN": "操作", "zh-TW": "操作"},
    "重试": {"zh-CN": "重试", "zh-TW": "重試"},
    "队列为空 — 提交 URL 或立即扫描。": {
        "zh-CN": "队列为空 — 提交 URL 或立即扫描。",
        "zh-TW": "佇列為空 — 提交 URL 或立即掃描。"},
    "仅支持 buondua.com 详情页链接": {
        "zh-CN": "仅支持 buondua.com 详情页链接",
        "zh-TW": "僅支援 buondua.com 詳情頁連結"},
    "URL 末尾无序号: {url}": {
        "zh-CN": "URL 末尾无序号: {url}",
        "zh-TW": "URL 結尾沒有序號:{url}"},
    "该写真(序号 {s})已处理过": {
        "zh-CN": "该写真(序号 {s})已处理过",
        "zh-TW": "該寫真(序號 {s})已處理過"},
    "任务已在队列中": {"zh-CN": "任务已在队列中", "zh-TW": "任務已在佇列中"},
    "已加入队列(序号 {s})": {
        "zh-CN": "已加入队列(序号 {s})",
        "zh-TW": "已加入佇列(序號 {s})"},
    "扫描 {n} 页,新任务 {m}": {
        "zh-CN": "扫描 {n} 页,新任务 {m}",
        "zh-TW": "掃描 {n} 頁,新任務 {m}"},
    "扫描失败: {e}": {"zh-CN": "扫描失败: {e}", "zh-TW": "掃描失敗:{e}"},
    "导入归档库": {"zh-CN": "导入归档库", "zh-TW": "匯入歸檔庫"},
    "把归档库(library)里的写真搬进平台:图片移到图片库、按模特归档、立即发布。下载完成的写真会自动导入,这里用于手动补导。": {
        "zh-CN": "把归档库(library)里的写真搬进平台:图片移到图片库、按模特归档、立即发布。下载完成的写真会自动导入,这里用于手动补导。",
        "zh-TW": "把歸檔庫(library)裡的寫真搬進平台:圖片移到圖片庫、按模特兒歸檔、立即發佈。下載完成的寫真會自動匯入,這裡用於手動補匯。"},
    "扫描归档库导入": {"zh-CN": "扫描归档库导入", "zh-TW": "掃描歸檔庫匯入"},
    "导入 {n} 个写真({p} 张照片),跳过 {s} 个": {
        "zh-CN": "导入 {n} 个写真({p} 张照片),跳过 {s} 个",
        "zh-TW": "匯入 {n} 個寫真({p} 張照片),跳過 {s} 個"},
    "导入 {n} 个写真({p} 张),失败 {e} 个": {
        "zh-CN": "导入 {n} 个写真({p} 张),失败 {e} 个",
        "zh-TW": "匯入 {n} 個寫真({p} 張),失敗 {e} 個"},
    "归档库为空 — 没有可导入的写真": {
        "zh-CN": "归档库为空 — 没有可导入的写真",
        "zh-TW": "歸檔庫為空 — 沒有可匯入的寫真"},

    # ---- Admin:设置页 -----------------------------------------------------------------
    "Admin Settings": {"zh-CN": "系统设置", "zh-TW": "系統設定"},
    "采集参数即时生效,存于 settings 表。": {
        "zh-CN": "采集参数即时生效,存于 settings 表。",
        "zh-TW": "採集參數即時生效,存於 settings 表。"},
    "采集": {"zh-CN": "采集", "zh-TW": "採集"},
    "站点": {"zh-CN": "站点", "zh-TW": "網站"},
    "定时扫描开启": {"zh-CN": "定时扫描开启", "zh-TW": "定時掃描開啟"},
    "扫描间隔(小时)": {"zh-CN": "扫描间隔(小时)", "zh-TW": "掃描間隔(小時)"},
    "每轮扫描页数": {"zh-CN": "每轮扫描页数", "zh-TW": "每輪掃描頁數"},
    "起始页(从新到旧)": {"zh-CN": "起始页(从新到旧)", "zh-TW": "起始頁(從新到舊)"},
    "白名单(每行一个关键词,留空 = 全收)": {
        "zh-CN": "白名单(每行一个关键词,留空 = 全收)",
        "zh-TW": "白名單(每行一個關鍵詞,留空 = 全收)"},
    "黑名单(优先级最高)": {"zh-CN": "黑名单(优先级最高)", "zh-TW": "黑名單(優先級最高)"},
    "黑名单(标题或标签命中即跳过)": {
        "zh-CN": "黑名单(标题或标签命中即跳过)",
        "zh-TW": "黑名單(標題或標籤命中即跳過)"},
    "模特名排除词(逗号分隔,按词匹配)": {
        "zh-CN": "模特名排除词(逗号分隔,按词匹配)",
        "zh-TW": "模特兒名排除詞(逗號分隔,按詞匹配)"},
    "从写真标签里挑模特名时,命中这些词就跳过(出品方/分类标签)。全部命中则归入「未分类」。": {
        "zh-CN": "从写真标签里挑模特名时,命中这些词就跳过(出品方/分类标签)。全部命中则归入「未分类」。",
        "zh-TW": "從寫真標籤裡挑模特兒名時,命中這些詞就跳過(出品方/分類標籤)。全部命中則歸入「未分類」。"},
    "未分类模特目录名": {"zh-CN": "未分类模特目录名", "zh-TW": "未分類模特兒目錄名"},
    "未分类": {"zh-CN": "未分类", "zh-TW": "未分類"},
    "归档根目录": {"zh-CN": "归档根目录", "zh-TW": "歸檔根目錄"},
    "当前:{d} — 通过环境变量 LIBRARY_DIR 修改,页面不可改(避免运行中换根)。": {
        "zh-CN": "当前:{d} — 通过环境变量 LIBRARY_DIR 修改,页面不可改(避免运行中换根)。",
        "zh-TW": "目前:{d} — 透過環境變數 LIBRARY_DIR 修改,頁面不可改(避免執行中換根)。"},
    "默认语言": {"zh-CN": "默认语言", "zh-TW": "預設語言"},
    "未登录访客与无个人设置用户看到的界面语言。": {
        "zh-CN": "未登录访客与无个人设置用户看到的界面语言。",
        "zh-TW": "未登入訪客與無個人設定使用者看到的介面語言。"},
    "保存设置": {"zh-CN": "保存设置", "zh-TW": "儲存設定"},
    "已保存": {"zh-CN": "已保存", "zh-TW": "已儲存"},

    # ---- Admin:列表页通用 ---------------------------------------------------------------
    "Published": {"zh-CN": "发布日期", "zh-TW": "發佈日期"},
    "Featured": {"zh-CN": "推荐", "zh-TW": "推薦"},
    "编辑": {"zh-CN": "编辑", "zh-TW": "編輯"},
    "删": {"zh-CN": "删", "zh-TW": "刪"},
    "删除写真 {t}?": {"zh-CN": "删除写真《{t}》?", "zh-TW": "刪除寫真《{t}》?"},
    "删除模特 {n}?其写真将一并删除。": {
        "zh-CN": "删除模特 {n}?其写真将一并删除。",
        "zh-TW": "刪除模特兒 {n}?其寫真將一併刪除。"},
    "删除标签 {n}?": {"zh-CN": "删除标签 {n}?", "zh-TW": "刪除標籤 {n}?"},
    "删除用户 {n}?": {"zh-CN": "删除用户 {n}?", "zh-TW": "刪除使用者 {n}?"},
    "{n} collections in total": {"zh-CN": "共 {n} 个写真集", "zh-TW": "共 {n} 個寫真集"},
    "{n} models in total": {"zh-CN": "共 {n} 位模特", "zh-TW": "共 {n} 位模特兒"},
    "{n} users": {"zh-CN": "{n} 位用户", "zh-TW": "{n} 位使用者"},

    # ---- Admin:写真集 ---------------------------------------------------------------------
    "Admin Collections": {"zh-CN": "写真集管理", "zh-TW": "寫真集管理"},
    "发布状态、归属模特与标签。": {
        "zh-CN": "发布状态、归属模特与标签。",
        "zh-TW": "發佈狀態、歸屬模特兒與標籤。"},
    "+ New collection": {"zh-CN": "+ 新建写真集", "zh-TW": "+ 新建寫真集"},
    "编辑写真": {"zh-CN": "编辑写真集", "zh-TW": "編輯寫真集"},
    "新建写真": {"zh-CN": "新建写真集", "zh-TW": "新建寫真集"},
    "创建后可再编辑照片与标签": {
        "zh-CN": "创建后可再编辑照片与标签",
        "zh-TW": "建立後可再編輯照片與標籤"},
    "标题 *": {"zh-CN": "标题 *", "zh-TW": "標題 *"},
    "Slug(留空自动)": {"zh-CN": "Slug(留空自动)", "zh-TW": "Slug(留空自動)"},
    "发布日期(YYYY.MM.DD)": {
        "zh-CN": "发布日期(YYYY.MM.DD)",
        "zh-TW": "發佈日期(YYYY.MM.DD)"},
    "首页推荐": {"zh-CN": "首页推荐", "zh-TW": "首頁推薦"},
    "保存": {"zh-CN": "保存", "zh-TW": "儲存"},
    "取消": {"zh-CN": "取消", "zh-TW": "取消"},
    "前台查看": {"zh-CN": "前台查看", "zh-TW": "前台檢視"},
    "标签": {"zh-CN": "标签", "zh-TW": "標籤"},
    "输入标签名": {"zh-CN": "输入标签名", "zh-TW": "輸入標籤名"},
    "添加": {"zh-CN": "添加", "zh-TW": "新增"},
    "点击移除": {"zh-CN": "点击移除", "zh-TW": "點擊移除"},
    "暂无标签": {"zh-CN": "暂无标签", "zh-TW": "暫無標籤"},
    "照片({n})": {"zh-CN": "照片({n})", "zh-TW": "照片({n})"},
    "文件位于 /media 下,按顺序排序。导入管线(采集归档)自动追加。": {
        "zh-CN": "文件位于 /media 下,按顺序排序。导入管线(采集归档)自动追加。",
        "zh-TW": "檔案位於 /media 下,按順序排序。匯入管線(採集歸檔)自動追加。"},
    "暂无照片 — 由采集导入管线或手动上传添加。": {
        "zh-CN": "暂无照片 — 由采集导入管线或手动上传添加。",
        "zh-TW": "暫無照片 — 由採集匯入管線或手動上傳新增。"},
    "slug-exists": {"zh-CN": "Slug 已存在", "zh-TW": "Slug 已存在"},
    "slug 已存在: {slug}": {
        "zh-CN": "slug 已存在: {slug}",
        "zh-TW": "slug 已存在:{slug}"},

    # ---- Admin:模特 -------------------------------------------------------------------------
    "Admin Models": {"zh-CN": "模特管理", "zh-TW": "模特兒管理"},
    "档案中的模特资料。": {"zh-CN": "档案馆中的模特资料。", "zh-TW": "檔案館中的模特兒資料。"},
    "+ New model": {"zh-CN": "+ 新建模特", "zh-TW": "+ 新建模特兒"},
    "Stage name": {"zh-CN": "艺名", "zh-TW": "藝名"},
    "编辑模特": {"zh-CN": "编辑模特", "zh-TW": "編輯模特兒"},
    "新建模特": {"zh-CN": "新建模特", "zh-TW": "新建模特兒"},
    "slug 留空则由名字生成": {"zh-CN": "slug 留空则由名字生成", "zh-TW": "slug 留空則由名字生成"},
    "名字 *": {"zh-CN": "名字 *", "zh-TW": "名字 *"},
    "艺名": {"zh-CN": "艺名", "zh-TW": "藝名"},
    "性别": {"zh-CN": "性别", "zh-TW": "性別"},
    "年龄": {"zh-CN": "年龄", "zh-TW": "年齡"},
    "身高": {"zh-CN": "身高", "zh-TW": "身高"},
    "三围": {"zh-CN": "三围", "zh-TW": "三圍"},
    "经纪公司": {"zh-CN": "经纪公司", "zh-TW": "經紀公司"},
    "简介": {"zh-CN": "简介", "zh-TW": "簡介"},

    # ---- Admin:标签 ----------------------------------------------------------------------------
    "Admin Tags": {"zh-CN": "标签管理", "zh-TW": "標籤管理"},
    "主题标签,用于筛选与发现。": {
        "zh-CN": "主题标签,用于筛选与发现。",
        "zh-TW": "主題標籤,用於篩選與發現。"},
    "新标签名": {"zh-CN": "新标签名", "zh-TW": "新標籤名"},
    "暂无标签。": {"zh-CN": "暂无标签。", "zh-TW": "暫無標籤。"},

    # ---- Admin:用户 -------------------------------------------------------------------------------
    "Admin Users": {"zh-CN": "用户管理", "zh-TW": "使用者管理"},
    "账号与角色管理。": {"zh-CN": "账号与角色管理。", "zh-TW": "帳號與角色管理。"},
    "密码(≥6 位)": {"zh-CN": "密码(≥6 位)", "zh-TW": "密碼(≥6 位)"},
    "创建": {"zh-CN": "创建", "zh-TW": "建立"},
    "用户名": {"zh-CN": "用户名", "zh-TW": "使用者名稱"},
    "改密码": {"zh-CN": "改密码", "zh-TW": "改密碼"},
    "新密码": {"zh-CN": "新密码", "zh-TW": "新密碼"},
    "重置": {"zh-CN": "重置", "zh-TW": "重設"},
    "改": {"zh-CN": "改", "zh-TW": "改"},
    "(你)": {"zh-CN": "(你)", "zh-TW": "(你)"},
    "密码至少 6 位": {"zh-CN": "密码至少 6 位", "zh-TW": "密碼至少 6 位"},
    "用户名已存在": {"zh-CN": "用户名已存在", "zh-TW": "使用者名稱已存在"},
    "不能删除自己": {"zh-CN": "不能删除自己", "zh-TW": "不能刪除自己"},
}


# ============================================================================
# JS 支持:app.js 所需的全部 msgid 随 boot_json 注入(仅 ~6KB)。
# ============================================================================

def js_strings(lang: str) -> dict[str, str]:
    """当前语言的全量映射(msgid → 译文);msgid 本身就是回退译文。"""
    out: dict[str, str] = {}
    for key, entry in STRINGS.items():
        out[key] = entry.get(lang) or entry.get("zh-CN") or key
    return out
