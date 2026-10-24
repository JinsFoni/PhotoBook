"""标题抽模特名 — 「系列 编号 名字」类老帖(4kup 2021 及更早)。

任务 825 实录:4kup 老帖标题形如 `MFStar Vol.076 Mu Yu Qian (慕羽茜)` /
`BoLoli Bol.054 Liu You Qi Sevenbaby (柳侑绮Sevenbaby)`。名字位固定在编号
之后,但白名单里只有 XIUREN / UGIRLS / IMISS / YouMi,MFStar、BoLoli 整批
落「未分类」。下面是用真帖标题做的回归语料(抽样自 4kup sitemap 老帖)。
"""

from __future__ import annotations

import pytest

from app.services.harvest.titlemodel import model_name_from_title

# (标题, 期望拉丁名, 期望原生名) —— 原生名允许为空
CASES = [
    ("MFStar Vol.076 Mu Yu Qian (慕羽茜)", "Mu Yu Qian", "慕羽茜"),
    ("MFStar Vol.189 Cao Mei Tu Tu (草莓兔兔)", "Cao Mei Tu Tu", "草莓兔兔"),
    ("MFStar Vol.188 Xia Xiao Xiao (夏笑笑Summer)", "Xia Xiao Xiao", "夏笑笑Summer"),
    ("MFStar Vol.191 任莹樱 Jenny", "任莹樱", ""),
    ("MFStar Vol.190 程程CC", "程程CC", ""),
    ("MFStar Vol.187 徐微微mia", "徐微微mia", ""),
    ("BoLoli Bol.054 Liu You Qi Sevenbaby (柳侑绮Sevenbaby)",
     "Liu You Qi Sevenbaby", "柳侑绮Sevenbaby"),
    ("BoLoli Bol.053 Jing Zi (靖子)", "Jing Zi", "靖子"),
    ("BoLoli Bol.051 Wang Yu Chun (王雨纯)", "Wang Yu Chun", "王雨纯"),
    ("BoLoli Bol.050 Xi Mu Zi (熙目子)", "Xi Mu Zi", "熙目子"),
]


@pytest.mark.parametrize("title,name,native", CASES)
def test_series_prefix_titles_keep_model_name(title, name, native):
    assert model_name_from_title(title) == (name, native)


def test_series_name_itself_is_not_the_model():
    """系列名(MFStar / BoLoli)绝不能被当成人名抽出来。"""
    for title, _n, _native in CASES:
        got = model_name_from_title(title)[0]
        assert got and got.lower() not in {"mfstar", "bololi"}, title


def test_series_rule_does_not_shadow_existing_prefixes():
    """原有的 XIUREN / YouMi / Coser@ 规则不受影响(新规则排在它们后面)。"""
    assert model_name_from_title("XIUREN No.1884 Yang Chen Chen (杨晨晨sugar)") \
        == ("Yang Chen Chen", "杨晨晨sugar")
    assert model_name_from_title("YouMi Vol.927 夏沫沫tifa") == ("夏沫沫tifa", "")
    assert model_name_from_title("Coser@Money冷冷 No.027 白挂") == ("Money冷冷", "")


def test_series_rule_wants_a_number_after_the_series():
    """没有编号就不是这套形态:宁可不抽,也不要把系列名当人。"""
    assert model_name_from_title("MFStar 慕羽茜 写真集") == ("", "")
