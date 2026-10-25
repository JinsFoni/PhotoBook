"""标题抽模特名 — 「系列 编号 名字」类老帖(4kup 2021 及更早)。

任务 825 实录:4kup 老帖标题形如 `MFStar Vol.076 Mu Yu Qian (慕羽茜)` /
`BoLoli Bol.054 Liu You Qi Sevenbaby (柳侑绮Sevenbaby)`。名字位固定在编号
之后,但白名单里只有 XIUREN / UGIRLS / IMISS / YouMi,MFStar、BoLoli 整批
落「未分类」。下面是用真帖标题做的回归语料(抽样自 4kup sitemap 老帖)。
"""

from __future__ import annotations

import pytest

from app.services.harvest.titlemodel import (model_name_from_title,
                                             native_name_for_model)

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
    # UGirls 的「U 编号」写法(2026-10-24:8 条老帖全落未分类的直接原因)
    ("UGirls U098 Mu Yu Qian (慕羽茜)", "Mu Yu Qian", "慕羽茜"),
    ("UGirls U258 Mu Fei Fei (穆菲菲)", "Mu Fei Fei", "穆菲菲"),
    ("UGIRLS No.258 Mu Fei Fei (穆菲菲)", "Mu Fei Fei", "穆菲菲"),
    # 系列名与编号之间夹日期(HuaYang 的写法)
    ("HuaYang 2017-09-25 Vol.007 Mu Fei Fei (穆菲菲)", "Mu Fei Fei", "穆菲菲"),
    ("HuaYang Vol.363 赵惟依coco", "赵惟依coco", ""),
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
    # 编号后面没有名字位(纯番号)同样不抽
    assert model_name_from_title("XIUREN No.313") == ("", "")


def test_series_banned_from_swallowing_street_shot_titles():
    """街拍批量标题(带 NO.xxxx + 货号)不能被当成模特名。"""
    for title in ("260921A70016-精选街拍作品 NO.5926 BYD展台车模[327P／216MB]",
                  "260915-7N0003-精选街拍作品 NO.5889 敏敏牛仔长腿[251P／494MB]"):
        assert model_name_from_title(title) == ("", ""), title


# ---- 原生名补全(misskon/buondua/nicesss 的模特名来自 tag,原名只在标题里) ----

def test_native_name_from_title_parenthesis():
    """名字后面紧跟的括号里是日文/中文原名 → 取出来写「又名」。"""
    assert native_name_for_model(
        "[JP] Asano Kokoro (浅野こころ): FRIDAYデジタル写真集 Sentimental (57 photos)",
        "Asano Kokoro") == "浅野こころ"
    assert native_name_for_model(
        "XIUREN No.962: Model Xiao Reba (小热巴) (44 photos)",
        "Xiao Reba") == "小热巴"
    # 全角括号同样认
    assert native_name_for_model(
        "[JP] Toyoda Runa（豊田ルナ） 週刊少年", "Toyoda Runa") == "豊田ルナ"


def test_native_name_skips_non_name_parentheses():
    """张数/系列括号不是原名;模特名本身就是中文名时不写同义重复。"""
    assert native_name_for_model("Some Post (57 photos)", "Some Model") == ""
    assert native_name_for_model("[Cosplay] 麻花麻花酱 (55 photos)",
                                 "麻花麻花酱") == ""
    # 标题里出现的是别人名字的括号 → 不认
    assert native_name_for_model("Asano Kokoro & Someone Else (小热巴)",
                                 "Asano Kokoro") == ""


def test_native_name_requires_same_person():
    """抽出的 (拉丁名, 原名) 必须是同一个人才算 —— 拉丁名对不上就退回括号法。"""
    assert native_name_for_model(
        "[JP] Ria Aise (藍瀬りあ) - 写真集 X (110 photos)", "Ria Aise") == "藍瀬りあ"
    # 名字写法不同(顺序换了)→ 不猜,宁可不写
    assert native_name_for_model(
        "[JP] Asano Kokoro (浅野こころ) - X", "Kokoro Asano") == ""
