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
