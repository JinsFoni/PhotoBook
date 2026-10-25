"""net 解析 — 序号提取、详情页字段(本地 HTML 样例,不发网络请求)。"""

from __future__ import annotations

import pytest

from app.services.harvest import net

REAL_URL = ("https://www.buondua.com/yeha-yeha-school-nurse-219-photos-"
            "6746d2e27adfd5224746c047dfc7b9fe-56616")


def test_serial_from_real_url():
    # 真实格式:<slug>-<hash>-<serial>,serial 为末段
    assert net._serial_from_url(REAL_URL) == 56616


def test_serial_plain():
    assert net._serial_from_url("https://www.buondua.com/abc-123") == 123


def test_serial_with_query():
    assert net._serial_from_url("https://www.buondua.com/abc-123?start=20") == 123


def test_serial_missing_raises():
    with pytest.raises(ValueError):
        net._serial_from_url("https://www.buondua.com/no-number-here")


DETAIL_HTML = """
<html><head><meta property="og:title" content="Yeha – School Nurse (219 photos)"></head>
<body>
<article>
<div class="article-info">
    <strong><small>Buondua</small></strong>
    -
    <small>
        09:10 29-10-2017            </small>
</div>
<div class="item-tags tags"><a class="tag" href="/tag/cosplay-10688"><span>Cosplay</span></a></div>
<div class="article-fulltext">
<p>Password: mrcong.com</p>
<a href="/tag/yeha-yeha-3881">yeha</a>
<a href="https://ouo.io/AbCdEf">link1</a>
<a href="https://ouo.press/XyZ123">link2</a>
<a href="https://ouo.io/AbCdEf">dup</a>
</div>
<div class="article-tags">
    <div class="tags">
    <a class="tag is-medium" href="/tag/yeha-11167">
        <span class="">Yeha</span>
    </a>
    </div>
</div>
</article>
</body></html>
"""


def _tags_html(pairs, extra_cards=""):
    """构造带 article-tags 容器的详情页(pairs = [(slug, 显示名)])。"""
    links = "".join(
        f'<a class="tag is-medium" href="/tag/{s}"><span class="">{n}</span></a>'
        for s, n in pairs)
    return (f'<html><head><meta property="og:title" content="T"></head><body>'
            f'{extra_cards}<div class="article-tags"><div class="tags">{links}</div></div>'
            f'</body></html>')


def test_parse_detail_page_fields():
    t = net.parse_detail_page(REAL_URL, existing_html=DETAIL_HTML)
    assert t.serial == 56616
    assert t.title == "Yeha – School Nurse (219 photos)"
    # 取 article-tags 里的显示名(不再是第一个 /tag/ 链接的 slug)
    assert t.model_name == "Yeha"
    assert t.tags == ["Yeha"]
    # 单一密码(无 " or ")保持原文,不追加候选
    assert t.password == "mrcong.com"
    # 短链去重保序
    assert t.shortlinks == ["https://ouo.io/AbCdEf", "https://ouo.press/XyZ123"]
    # Joomla article-info 的发布时间(日-月-年)→ YYYY.MM.DD
    assert t.published == "2017.10.29"


def test_model_name_ignores_related_card_tags():
    """回归:相关推荐卡片(.item-tags)里的 tag 绝不能当模特名。"""
    html = _tags_html(
        [("yeha-11167", "Yeha")],
        extra_cards='<div class="item-tags tags">'
                    '<a href="/tag/cosplay-10688"><span>Cosplay</span></a></div>')
    t = net.parse_detail_page(REAL_URL, existing_html=html)
    assert t.model_name == "Yeha"
    assert t.tags == ["Yeha"]


def test_model_name_skips_publisher_tag():
    html = _tags_html([("cosplay-10688", "Cosplay"), ("mahua-13503", "麻花麻花酱")])
    t = net.parse_detail_page(REAL_URL, existing_html=html)
    assert t.model_name == "麻花麻花酱"
    assert t.tags == ["Cosplay", "麻花麻花酱"]


def test_model_name_all_excluded_is_empty():
    html = _tags_html([("jp-11853", "JP"), ("ai-generated-11406", "AI Generated")])
    t = net.parse_detail_page(REAL_URL, existing_html=html)
    assert t.model_name == ""
    assert t.tags == ["JP", "AI Generated"]


def test_model_name_custom_exclude():
    html = _tags_html([("yeha-11167", "Yeha"), ("cosplay-10688", "Cosplay")])
    t = net.parse_detail_page(REAL_URL, existing_html=html, model_exclude="yeha")
    assert t.model_name == "Cosplay"


def test_parse_detail_no_tags_container():
    t = net.parse_detail_page(REAL_URL, existing_html="<html><body>nothing</body></html>")
    assert t.model_name == "" and t.tags == []


def test_parse_detail_strips_page_suffix():
    html = DETAIL_HTML.replace(
        'content="Yeha – School Nurse (219 photos)"',
        'content="Yeha – School Nurse ( Page 3 / 8 )"')
    t = net.parse_detail_page("https://www.buondua.com/x-1", existing_html=html)
    assert "Page" not in t.title


# ---- nicesss 详情页 -----------------------------------------------------------

NICESSS_URL = "https://www.nicesss.com/archives/xr/xiurw/464006.html"

NICESSS_HTML = """
<html><head>
<title>[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社</title>
<meta name="description" content="[解壓密碼-Password]：sssins.com [下載網盤]：MediaFire">
<meta property="og:title" content="[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社">
<script type="application/ld+json">{"@context":"http:\\/\\/schema.org","@type":"Article","datePublished":"2026-01-30T18:00:00+08:00"}</script>
</head><body>
<article class="article-content">
<h1 class="entry-title"><a href="URL">[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB]</a></h1>
<p><a href="https://ouo.io/GA80ao5"><span>Download</span><span>FREE</span></a></p>
<font color="#FFB6C1">[解壓密碼-Password]：sssins.com</font><br />
<font color="#70DB93">[下載網盤-Download]：MediaFire</font>
<!-- 侧边栏标签云(全站热门,与本页无关): -->
<a href="https://www.nicesss.com/archives/tag/%e5%a6%b2%e5%b7%b1">妲己</a>
</article></body></html>
""".replace("URL", NICESSS_URL)


def test_nicesss_is_nicesss_url():
    assert net.is_nicesss_url(NICESSS_URL)
    assert net.is_nicesss_url("https://nicesss.com/archives/xr/xiurw/1.html")
    assert not net.is_nicesss_url("https://www.buondua.com/x-1")
    assert not net.is_nicesss_url("https://www.nicesss.com.evil.example/x")


def test_nicesss_serial():
    assert net._serial_from_nicesss_url(NICESSS_URL) == 464006
    assert net.serial_from_url(NICESSS_URL) == 464006
    with pytest.raises(ValueError):
        net._serial_from_nicesss_url("https://www.nicesss.com/archives/xr/xiurw/no.htmlx")


def test_nicesss_parse_detail_fields():
    t = net.parse_detail_page(NICESSS_URL, existing_html=NICESSS_HTML)
    assert t.serial == 464006
    assert t.title == "[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB]"
    # 模特名来自标题,同时作为 tag(前面是出品方)
    assert t.model_name == "妲己_Toxic"
    assert t.tags == ["Xiuren秀人网", "妲己_Toxic"]
    # 密码取正文 <font> 里的,不被 meta description 的同名文字干扰
    assert t.password == "sssins.com"
    # 短链正文挂两遍,去重保序
    assert t.shortlinks == ["https://ouo.io/GA80ao5"]
    # JSON-LD datePublished(斜杠转义)→ YYYY.MM.DD
    assert t.published == "2026.01.30"


def test_nicesss_password_plain_text_variant():
    """老帖密码无 <font> 包裹:简体纯文本 "[解压密码]：xxx<br />"。"""
    html = NICESSS_HTML.replace(
        '<font color="#FFB6C1">[解壓密碼-Password]：sssins.com</font>',
        '[解压密码]：vx666878787<br />')
    t = net.parse_nicesss_detail_page(NICESSS_URL, existing_html=html)
    assert t.password == "vx666878787"


def test_nicesss_parse_xingyan_vol_title():
    html = NICESSS_HTML.replace(
        'content="[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社"',
        'content="[XINGYAN星颜社]2026.01.21 VOL.456 时安安[82+1P／910MB] - 呦糖社"')
    t = net.parse_nicesss_detail_page(NICESSS_URL, existing_html=html)
    assert t.model_name == "时安安"
    assert t.tags == ["XINGYAN星颜社", "时安安"]


def test_nicesss_parse_no_publisher_in_title():
    """无方括号头/尾的怪标题 → 模特名为空,不得误切。"""
    html = NICESSS_HTML.replace(
        'content="[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社"',
        'content="随便一个标题 - 呦糖社"')
    t = net.parse_nicesss_detail_page(NICESSS_URL, existing_html=html)
    assert t.model_name == "" and t.tags == []


def test_serial_from_url_dispatch():
    # 同名分派入口:buondua 走尾段, misskon 走 slug 前缀, nicesss 走 <id>.html
    assert net.serial_from_url(
        "https://www.buondua.com/yeha-x-56616") == 56616
    assert net.serial_from_url(NICESSS_URL) == 464006
    assert net.serial_from_url(MISSKON_URL) == 119420


# ---- misskon 详情页 -----------------------------------------------------------

MISSKON_URL = "https://misskon.com/119420-bluecake-lee-ahrin-red-night-255-photos/"

MISSKON_HTML = """
<html><head><title>[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos) – MissKon.com</title>
<script type="application/ld+json">{"@context":"http:\\/\\/schema.org","@type":"Article","datePublished":"2026-10-12T06:51:19+08:00"}</script></head>
<body>
<article class="item-list">
  <div class="post-thumbnail"><a href="https://misskon.com/119420-bluecake-lee-ahrin-red-night-255-photos/"><img src="cover.jpg"></a></div>
  <h2 class="post-box-title"><a href="https://misskon.com/119420-bluecake-lee-ahrin-red-night-255-photos/">[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos)</a></h2>
</article>
<div class="post-inner">
  <h1 class="name post-title entry-title">[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos)</h1>
  <div class="entry">
    <strong>Password unrar:</strong> <span style="color: #2cbb6b">misskon.com</span><br />
    <p style="text-align: center"><a href="https://ouo.io/F3FYal" target="_blank" class="shortc-button"><i class="fa fa-download"></i>Download link: MediaFire</a></p>
    <p><a href="https://1024terabox.com/s/xyz">TeraBox backup</a></p>
  </div>
  <p class="post-tag">Tags<a href="https://misskon.com/tag/bluecake/" rel="tag">BLUECAKE</a> <a href="https://misskon.com/tag/lee-ahrin/" rel="tag">Lee Ahrin</a></p>
</div>
</body></html>
"""


def test_misskon_is_misskon_url():
    assert net.is_misskon_url(MISSKON_URL)
    assert net.is_misskon_url("https://www.misskon.com/x")
    assert not net.is_misskon_url("https://buondua.com/x")
    assert not net.is_misskon_url("https://misskon.com.evil.example/x")


def test_misskon_serial():
    assert net._serial_from_misskon_url(MISSKON_URL) == 119420
    assert net.serial_from_url(MISSKON_URL) == 119420
    # 分卷文章尾段 /2/ /3/ 无序号,取 slug 前缀
    assert net._serial_from_misskon_url(
        "https://misskon.com/119400-otherxxx-sy-674-photos/2/") == 119400
    # query/fragment 不干扰
    assert net._serial_from_misskon_url(
        "https://misskon.com/119384-coser-du-50-photos/?x=1") == 119384
    with pytest.raises(ValueError):
        net._serial_from_misskon_url("https://misskon.com/about-us/")


def test_misskon_parse_detail_fields():
    t = net.parse_detail_page(MISSKON_URL, existing_html=MISSKON_HTML)
    assert t.serial == 119420
    assert t.title == "[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos)"
    # tag 顺序与 buondua 相反(misskon 模特名在前),模特名挑取结果一致
    assert t.model_name == "Lee Ahrin"
    assert t.tags == ["BLUECAKE", "Lee Ahrin"]
    assert t.password == "misskon.com"
    # 锚文本 MediaFire 的 ouo 主链 + 直挂的 TeraBox 备份链。760 起后者不再被
    # 丢掉:备链只在 MF 全废时由 worker 兜底启用,主源优先级不变
    assert t.shortlinks == ["https://ouo.io/F3FYal",
                            "https://1024terabox.com/s/xyz"]
    # JSON-LD datePublished → YYYY.MM.DD
    assert t.published == "2026.10.12"


def test_misskon_password_input_variant():
    """老文章密码是 <input value="..."> 形态而非 <span>。"""
    html = MISSKON_HTML.replace(
        '<span style="color: #2cbb6b">misskon.com</span>',
        '<input type="text" size="11" readonly value="misskon.com">')
    t = net.parse_misskon_detail_page(MISSKON_URL, existing_html=html)
    assert t.password == "misskon.com"


def test_misskon_parse_via_dispatch():
    """分派入口走 misskon 分支(与 buondua 解析器选择器不同)。"""
    t = net.parse_detail_page(MISSKON_URL, existing_html=MISSKON_HTML)
    assert t.model_name == "Lee Ahrin"   # buondua 解析器在此 HTML 上取不到 tag


MISSKON_LEGACY_URL = "https://misskon.com/xiuren-no-962-model-xiao-reba-44-photos"


def _clear_misskon_serial_cache():
    """老帖序号解析结果按 URL 进程级缓存(生产特性), 同一 URL 在多个
    用例间复用时必须清, 否则 mock 的页面内容不生效。"""
    net._misskon_serial_cache.clear()
MISSKON_LEGACY_HTML = """
<html><head><title>XIUREN No.962: Model Xiao Reba (小热巴) (44 photos) – MissKon.com</title></head>
<body class="post-template-default single single-post postid-25634">
  <h1 class="name post-title entry-title">XIUREN No.962: Model Xiao Reba (小热巴) (44 photos)</h1>
  <div class="entry">
    <strong>Password unrar:</strong> <span style="color: #2cbb6b">misskon.com</span>
    <a href="https://ouo.io/F3FYal">Download link: MediaFire</a>
  </div>
  <p class="post-tag">Tags<a href="https://misskon.com/tag/xiuren/" rel="tag">XIUREN</a> <a href="https://misskon.com/tag/xiao-reba/" rel="tag">Xiao Reba</a></p>
</body></html>
"""


def test_misskon_legacy_url_serial_from_postid(monkeypatch):
    """老帖 slug 无 <序号>- 前缀 → 序号回退页面 body 的 postid-N。"""
    _clear_misskon_serial_cache()
    monkeypatch.setattr(net, "fetch_html",
                        lambda url, **kw: MISSKON_LEGACY_HTML)
    assert net.serial_from_url(MISSKON_LEGACY_URL) == 25634


def test_misskon_legacy_parse_detail(monkeypatch):
    """老式 URL 详情解析:序号来自页面,标题/模特/密码/短链同新式。"""
    t = net.parse_detail_page(MISSKON_LEGACY_URL,
                              existing_html=MISSKON_LEGACY_HTML)
    assert t.serial == 25634
    assert t.title == "XIUREN No.962: Model Xiao Reba (小热巴) (44 photos)"
    assert t.model_name == "Xiao Reba"
    assert t.password == "misskon.com"
    assert t.shortlinks == ["https://ouo.io/F3FYal"]


def test_misskon_legacy_unzip_password_variant():
    """老帖密码写法是 "Unzip password:</strong> <input value=...>"。"""
    html = MISSKON_LEGACY_HTML.replace(
        '<strong>Password unrar:</strong> <span style="color: #2cbb6b">misskon.com</span>',
        '<strong>Unzip password:</strong> <input type="text" size="11" readonly value="mrcong.com">')
    t = net.parse_misskon_detail_page(MISSKON_LEGACY_URL, existing_html=html)
    assert t.password == "mrcong.com"


def test_misskon_direct_mediafire_link():
    """老帖不挂 ouo 短链,直接放 MediaFire 链接 → 进 shortlinks(顺序:MF 先)。"""
    html = MISSKON_HTML.replace(
        '<a href="https://ouo.io/F3FYal" target="_blank" class="shortc-button"><i class="fa fa-download"></i>Download link: MediaFire</a>',
        '<a href="http://www.mediafire.com/file/abc123/XIUREN_No.1577.rar/file" target="_blank">Download</a>')
    t = net.parse_misskon_detail_page(MISSKON_URL, existing_html=html)
    assert t.shortlinks == [
        "http://www.mediafire.com/file/abc123/XIUREN_No.1577.rar/file",
        "https://1024terabox.com/s/xyz"]


@pytest.mark.parametrize("url,key", [
    ("https://www.mediafire.com/file/abc123?action=check", "abc123"),
    ("https://www.mediafire.com/file/abc123/?action=check", "abc123"),
    ("https://www.mediafire.com/file/abc123/XIUREN_No.1577.rar/file", "abc123"),
    ("https://www.mediafire.com/file/abc123", "abc123"),
])
def test_mf_key_re_accepts_query_string(url, key):
    """MediaFire 把 /file/<key>/ 302 到 /file/<key>/?action=check —— 带查询串的
    落地 URL 也必须能取到 quick_key(2026-10-20 两条采集任务卡在这一步)。"""
    m = net.MF_KEY_RE.search(url)
    assert m and m.group(1) == key


def test_mediafire_info_from_action_check_url(monkeypatch):
    """落地 URL 是 ?action=check 形态时,get_info 仍要能走通并带出大小/哈希。"""

    class _Resp:
        status_code = 200
        headers: dict = {}
        text = ""

        def json(self):
            return {"response": {"file_info": {
                "size": "1056953678", "hash": "AB12EF", "filename": "x.rar"}}}

    class _Sess:
        def close(self):
            pass

    monkeypatch.setattr(net.cr, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(
        net, "mediafire_page_session",
        lambda url, **kw: ('<a href="https://download1475.mediafire.com/x">',
                           _Sess()))
    info = net.mediafire_info_from_url(
        "https://www.mediafire.com/file/lff2y9wctjycelj?action=check")
    assert info["quick_key"] == "lff2y9wctjycelj"
    assert info["size"] == 1056953678
    assert info["sha256"] == "ab12ef"
    assert info["direct_url"].startswith("https://download1475.mediafire.com/")
    assert "_session" not in info  # 默认不交出会话


def test_mediafire_info_hands_back_session_for_download(monkeypatch):
    """keep_session=True:把取页面那份 Session 交出来 —— 直链 dkey 绑客户端,
    下载换个无 cookie 的连接会被塞 download_repair 验证页(2026-10-22 实测)。

    取页面用 API 的 canonical 链接(这里 file_info 没给 links → 回退裸 key
    页),不用传进来的 URL:ouo 的 302 Location 会截断(760)。
    """

    class _Resp:
        status_code = 200
        headers: dict = {}
        text = ""
        seen_params = []

        def json(self):
            return {"response": {"file_info": {
                "size": "1", "hash": "AA", "filename": "x.rar"}}}

    sess = object()
    fetched = []

    class _S:
        closed = False

        def close(self):
            _S.closed = True

    monkeypatch.setattr(net.cr, "get", lambda *a, **k: _Resp())

    def _page_session(url, **kw):
        fetched.append(url)
        return 'href="https://download9.mediafire.com/y"', _S()

    monkeypatch.setattr(net, "mediafire_page_session", _page_session)
    info = net.mediafire_info_from_url(
        "https://www.mediafire.com/file/abc123/x.rar", keep_session=True)
    assert isinstance(info["_session"], _S)
    assert fetched == ["https://www.mediafire.com/file/abc123/"]
    assert info["_referer"] == "https://www.mediafire.com/file/abc123/"
    assert _S.closed is False
    assert sess is not None


def test_mediafire_info_prefers_api_canonical_page(monkeypatch):
    """页面走 API 给的 links.normal_download:传进来的 URL 可能被截断(760)。"""

    class _Resp:
        status_code = 200
        headers: dict = {}
        text = ""

        def json(self):
            return {"response": {"file_info": {
                "size": "1", "hash": "AA", "filename": "x.rar",
                "links": {"normal_download":
                          "https://www.mediafire.com/file/abc123/x.rar/file"}}}}

    fetched = []

    class _S:
        def close(self):
            pass

    monkeypatch.setattr(net.cr, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(net, "mediafire_page_session",
                        lambda url, **kw: (fetched.append(url),
                                           'href="https://download9.mediafire.com/y"',
                                           _S())[1:])
    info = net.mediafire_info_from_url(
        "https://www.mediafire.com/file/abc123/%5BJP%5D_x_%E4%B8%83%E",  # 截断的落地 URL
        keep_session=True)
    assert fetched == ["https://www.mediafire.com/file/abc123/x.rar/file"]
    assert info["quick_key"] == "abc123"
    assert info["direct_url"] == "https://download9.mediafire.com/y"


def test_misskon_legacy_no_postid_raises(monkeypatch):
    """既无 slug 序号又无 postid → 仍报 ValueError(回中文消息)。"""
    _clear_misskon_serial_cache()  # 同 URL 可能被上一个用例缓存过成功结果
    monkeypatch.setattr(
        net, "fetch_html",
        lambda url, **kw: "<html><body><h1>404</h1></body></html>")
    with pytest.raises(ValueError):
        net.serial_from_url(MISSKON_LEGACY_URL)


def test_misskon_scan_list_page(monkeypatch):
    """列表扫描:只取 article.item-list 正文卡片(侧栏热门不算),分页 /page/N/。"""
    html = """
    <article class="item-list">
      <div class="post-thumbnail"><a href="https://misskon.com/119384-coser-du-jiu-50-photos/"><img></a></div>
    </article>
    <article class="item-list">
      <div class="post-thumbnail"><a href="https://misskon.com/119386-otherxxx-nancyyzp-64-photos/"><img></a></div>
    </article>
    <!-- 侧栏 widget: 同形态链接但不在 article 里 -->
    <div class="widget"><a href="https://misskon.com/88779-coser-hana-bunny-19-photos/">old hot</a></div>
    <a href="https://misskon.com/page/2/">Next</a>
    """
    monkeypatch.setattr(net, "fetch_html", lambda url, **kw: html)
    links, has_next = net.scan_misskon_list_page("https://misskon.com/")
    assert links == [
        (119384, "https://misskon.com/119384-coser-du-jiu-50-photos/"),
        (119386, "https://misskon.com/119386-otherxxx-nancyyzp-64-photos/"),
    ]
    assert has_next is True


# ---- MediaFire 的 Cloudflare 抽检(2026-10-22) --------------------------------

class _CfResp:
    def __init__(self, status=200, body="", headers=None):
        self.status_code = status
        self.text = body
        self.headers = headers or {}


def test_is_cf_challenge_by_header_and_body():
    assert net.is_cf_challenge(_CfResp(403, "x", {"cf-mitigated": "challenge"}))
    assert net.is_cf_challenge(_CfResp(403, "<title>Just a moment...</title>"))
    # 200 的盾页也算(CF 有时用 200 返回挑战页)
    assert net.is_cf_challenge(_CfResp(200, "<title>Just a moment...</title>"))
    # 正常页面 / 纯 403 无标记 → 不算
    assert not net.is_cf_challenge(_CfResp(200, "<html>ok</html>"))
    assert not net.is_cf_challenge(_CfResp(403, "forbidden"))


def test_mediafire_page_primes_session_then_gets_page(monkeypatch):
    """同一 Session 先打裸页(拿 __cf_bm)再打目标页 —— 一次就过。"""
    seen = []

    class _Sess:
        def __init__(self, **kw):
            self.kw = kw
            seen.append(("new", kw.get("proxy")))

        def get(self, url, **kw):
            seen.append(("get", url))
            if "?" in url:  # 目标页(action=check)
                return _CfResp(200, '<a href="https://download1.mediafire.com/x">')
            return _CfResp(200, "<html>prime</html>")

        def close(self):
            pass

    monkeypatch.setattr(net.cr, "Session", _Sess)
    monkeypatch.setattr(net, "_proxy", lambda: None)
    url = "https://www.mediafire.com/file/abc123?action=check"
    html = net.mediafire_page(url)
    assert "download1.mediafire.com" in html
    # 预热用的是去掉查询串的裸文件页,顺序在目标页之前
    assert [x for x in seen if x[0] == "get"] == [
        ("get", "https://www.mediafire.com/file/abc123/"), ("get", url)]


def test_mediafire_page_retries_challenge_then_succeeds(monkeypatch):
    """首轮被盾 → 换新 Session 重试 → 通过(不再一次失败整任务判死)。"""
    state = {"target": 0, "sessions": 0}

    class _Sess:
        def __init__(self, **kw):
            state["sessions"] += 1

        def get(self, url, **kw):
            if "?" not in url:  # 预热裸页:正常
                return _CfResp(200, "<html>prime</html>")
            state["target"] += 1
            if state["target"] == 1:  # 首轮目标页被盾
                return _CfResp(403, "<title>Just a moment...</title>",
                               {"cf-mitigated": "challenge"})
            return _CfResp(200, '<a href="https://download2.mediafire.com/y">')

        def close(self):
            pass

    monkeypatch.setattr(net.cr, "Session", _Sess)
    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    html = net.mediafire_page("https://www.mediafire.com/file/abc123?action=check")
    assert "download2.mediafire.com" in html
    assert state["target"] == 2
    assert state["sessions"] == 2  # 第 1 轮被盾后用新 Session 重来


def test_mediafire_page_gives_up_with_clear_error(monkeypatch):
    class _Sess:
        def __init__(self, **kw):
            pass

        def get(self, url, **kw):
            return _CfResp(403, "<title>Just a moment...</title>",
                           {"cf-mitigated": "challenge"})

        def close(self):
            pass

    monkeypatch.setattr(net.cr, "Session", _Sess)
    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as ei:
        net.mediafire_page("https://www.mediafire.com/file/abc123?action=check")
    assert "cf challenge" in str(ei.value)


def test_mf_api_get_retries_challenge(monkeypatch):
    """get_info.php 本身也可能被盾 —— 同样退避重试。"""
    calls = {"n": 0}

    class _J:
        def __init__(self, ok):
            self.ok = ok
            self.status_code = 200 if ok else 403
            self.text = "" if ok else "<title>Just a moment...</title>"
            self.headers = {}

        def json(self):
            return {"response": {"file_info": {
                "size": "1", "hash": "AA", "filename": "x.rar"}}}

    def fake_get(url, **kw):
        calls["n"] += 1
        return _J(calls["n"] > 1)

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net, "_proxy", lambda: None)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    r = net._mf_api_get("https://www.mediafire.com/api/1.5/file/get_info.php",
                        params={"quick_key": "abc"})
    assert r.status_code == 200 and calls["n"] == 2


# ---- 已停用的第三方短链(老视频帖) -------------------------------------------

# 2016-2017 的视频帖把下载按钮挂在 shink.me / adf.ly 上,这两个服务现在都废了
# (2026-10-24 实查:shink.me 域名进 ParkLogic 停放页,adf.ly 全量 302 到
# linkvertise)。页面形态照 misskon FEILIN Video No.031 抄。
DEAD_LINK_HTML = """
<html><head><title>FEILIN Video No.031: Model Mu Yu Qian (慕羽茜) – MissKon.com</title>
<script type="application/ld+json">{"@type":"Article","datePublished":"2017-01-16T08:06:49+08:00"}</script></head>
<body class="post-template-default single single-post postid-15464">
  <h1 class="name post-title entry-title">FEILIN Video No.031: Model Mu Yu Qian (慕羽茜)</h1>
  <div class="entry">
    <div class="box info"><strong>File size:</strong> 557MB</div>
    <p style="text-align: center;">Download video<br />
      <a href="http://shink.me/wyxfh" target="_blank" class="shortc-button medium green "><i class="fa fa-download"></i>Download link: Google Drive</a></p>
    <p><a href="http://adf.ly/1gPRzU" target="_blank">Download link: Google Drive (mirror)</a></p>
  </div>
  <p class="post-tag">Tags<a href="https://misskon.com/tag/feilin/" rel="tag">FEILIN</a></p>
</body></html>
"""


def test_dead_shortener_page_has_no_usable_links():
    """整页只有已停用的短链 → shortlinks 为空, 服务名进 dead_shortlinks。"""
    t = net.parse_misskon_detail_page("https://misskon.com/15464-feilin-video-no-031/",
                                      existing_html=DEAD_LINK_HTML)
    assert t.title.startswith("FEILIN Video No.031")
    assert t.shortlinks == []
    assert t.dead_shortlinks == ["shink.me", "adf.ly"]


def test_dead_shortener_recorded_alongside_working_link():
    """有可用短链时也照记:报错文案不会用到,但别把页面信息丢了。"""
    html = DEAD_LINK_HTML.replace(
        '<p class="post-tag">',
        '<p><a href="https://ouo.io/F3FYal">Download link: MediaFire</a></p>\n  <p class="post-tag">')
    t = net.parse_misskon_detail_page("https://misskon.com/15464-feilin-video-no-031/",
                                      existing_html=html)
    assert t.shortlinks == ["https://ouo.io/F3FYal"]
    assert t.dead_shortlinks == ["shink.me", "adf.ly"]


def test_dead_shortener_dedupes_by_service():
    """同一服务多条只报一次;linkvertise 新旧两个域名算同一服务。"""
    html = ('<html><body class="postid-1">'
            '<a href="http://shink.me/aaa">x</a><a href="https://shink.me/bbb">y</a>'
            '<a href="https://linkvertise.com/253297/x">z</a>'
            '<a href="https://linkvertise.net/abc">w</a></body></html>')
    t = net.parse_misskon_detail_page("https://misskon.com/1-x/", existing_html=html)
    assert t.dead_shortlinks == ["shink.me", "linkvertise"]


# ---- fetch_html:连接层抖动重试(2026-10-25 任务 869) ----------------------

class _FakeResp:
    def __init__(self, status_code=200, text="<html>ok</html>"):
        self.status_code = status_code
        self.text = text


def _conn_reset():
    """真帖复现的异常:curl_cffi 的 ConnectionError,消息里带 curl(35)。"""
    from curl_cffi.requests.exceptions import ConnectionError as CurlConnError
    return CurlConnError(
        "Failed to perform, curl: (35) Recv failure: Connection reset by peer.")


def test_fetch_html_retries_connection_reset(monkeypatch):
    """被对端 reset 一次不该判死整个采集任务(869 实录:零重试 → 5 秒 failed)。"""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        if len(calls) < 3:
            raise _conn_reset()
        return _FakeResp(text="<html>page</html>")

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    assert net.fetch_html("https://misskon.com/120229-x/") == "<html>page</html>"
    assert len(calls) == 3


def test_fetch_html_retry_exhausted_keeps_original_reason(monkeypatch):
    """重试用尽:报错仍要能看出是 curl 35(而不是笼统的「取页失败」)。"""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise _conn_reset()

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as ei:
        net.fetch_html("https://misskon.com/120229-x/")
    msg = str(ei.value)
    assert "curl: (35)" in msg and "已重试 3 次" in msg
    assert len(calls) == net.FETCH_RETRIES


def test_fetch_html_does_not_retry_http_error(monkeypatch):
    """404/403 是站点的确定答复:一次就报,不浪费重试预算。"""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return _FakeResp(status_code=404, text="nope")

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as ei:
        net.fetch_html("https://misskon.com/gone/")
    assert "HTTP 404" in str(ei.value)
    assert len(calls) == 1


def test_fetch_html_does_not_retry_bad_url(monkeypatch):
    """参数级错误(URL 非法)重试无意义。"""
    from curl_cffi.requests.exceptions import InvalidURL
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise InvalidURL("no scheme")

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        net.fetch_html("misskon.com/no-scheme")
    assert len(calls) == 1


def test_fetch_html_retries_param(monkeypatch):
    """retries=1 → 单次尝试(列表页这类可代价低的取页可显式关掉)。"""
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise _conn_reset()

    monkeypatch.setattr(net.cr, "get", fake_get)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        net.fetch_html("https://misskon.com/120229-x/", retries=1)
    assert len(calls) == 1


# ---- 模特原生名(model_native)—— 三家站点的模特名来自 tag,原名只在标题里 ----

ASANO_BUONDUA_HTML = """
<html><head><meta property="og:title" content="[JP] Asano Kokoro (浅野こころ) - FRIDAYデジタル写真集 Sentimental (57 photos)"></head>
<body><div class="article-tags"><div class="tags">
<a class="tag is-medium" href="/tag/asano-kokoro-1"><span class="">Asano Kokoro</span></a>
</div></div></body></html>
"""


def test_buondua_detail_carries_model_native():
    """模特名取 tag,原名取标题里的括号 —— 一并带出,导入时写 stage_name。"""
    t = net.parse_detail_page(REAL_URL, existing_html=ASANO_BUONDUA_HTML)
    assert t.model_name == "Asano Kokoro"
    assert t.model_native == "浅野こころ"


def test_misskon_detail_carries_model_native():
    t = net.parse_detail_page(MISSKON_LEGACY_URL, existing_html=MISSKON_LEGACY_HTML)
    assert t.model_name == "Xiao Reba"
    assert t.model_native == "小热巴"


def test_nicesss_model_native_empty_when_name_is_native():
    """名字位本身就是中文名 → 不写同义「又名」。"""
    t = net.parse_nicesss_detail_page(NICESSS_URL, existing_html=NICESSS_HTML)
    assert t.model_name == "妲己_Toxic"
    assert t.model_native == ""


def test_nicesss_splits_latin_and_native_in_name_slot():
    """名字位是「Latin (原名)」时拆开:不能建出带括号的模特条目。"""
    html = NICESSS_HTML.replace(
        'content="[Xiuren秀人网]2026.01.30 NO.11301 妲己_Toxic[70+1P／959MB] - 呦糖社"',
        'content="[Xiuren秀人网]2026.01.30 NO.11301 Asano Kokoro (浅野こころ)[70+1P／959MB] - 呦糖社"')
    t = net.parse_nicesss_detail_page(NICESSS_URL, existing_html=html)
    assert t.model_name == "Asano Kokoro"
    assert t.model_native == "浅野こころ"


def test_tag_name_with_parenthesised_native_is_split():
    """tag 本身写成「Latin (原名)」时同样拆开(不新建带括号的模特)。"""
    html = _tags_html([("asano-kokoro", "Asano Kokoro (浅野こころ)")])
    t = net.parse_detail_page(REAL_URL, existing_html=html)
    assert t.model_name == "Asano Kokoro"
    assert t.model_native == "浅野こころ"
