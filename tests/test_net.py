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
<html><head><title>[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos) – MissKon.com</title></head>
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
    # 直挂的 TeraBox 备份链不是 ouo 域,天然滤掉;只留锚文本 MediaFire 的 ouo 链
    assert t.shortlinks == ["https://ouo.io/F3FYal"]


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
