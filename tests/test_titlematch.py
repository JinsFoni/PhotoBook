"""跨站标题比对 — titles_match 的判据(真实站点标题采样)。

三个源站对同一本写有的标题写法不同(buondua og:title / misskon h1 /
nicesss og:title),且同一站在不同期的写真标题高度相似。判据必须
同时做到:同作品跨站命中, 同模特不同作品、同系列不同期不误配。
"""

from __future__ import annotations

from app.services.harvest.titlematch import title_tokens, titles_match


# ---- 正例:同一本写真, 三站标题 -------------------------------------------------

def test_match_buondua_vs_archive_dir():
    """buondua og:title vs 采集归档目录名(= collections.title)。"""
    assert titles_match(
        "XIUREN No.6282: Daji_Toxic (妲己_Toxic) (71 photos) -",
        "XIUREN No.6282 Daji_Toxic (妲己_Toxic)")


def test_match_misskon_vs_archive_dir():
    assert titles_match(
        "Suji (수지): Eat The Delivery Man (63 photos)",
        "suji suji (수지) eat the delivery man")


def test_match_buondua_vs_misskon():
    """用户报的那本: buondua 56556 ↔ misskon 117727,标题写法差很多。"""
    assert titles_match(
        "YeonYu (연유): Blue (101 photos + 6 videos)  -",
        "yeonyu yeonyu (연유) blue")


def test_match_nicesss_vs_archive_dir():
    assert titles_match(
        "YeonYu (연유) - Blue [101P + 6V／585.6MB]",
        "yeonyu yeonyu (연유) blue")


def test_match_misskon_extra_word_in_title():
    """misskon 标题多一个 "Model",归档目录名里没有。"""
    assert titles_match(
        "XIUREN No.962: Model Xiao Reba (小热巴) (44 photos)",
        "XIUREN No.962 Xiao Reba (小热巴)")


def test_match_publisher_prefix_stripped():
    assert titles_match(
        "[BLUECAKE] Lee Ahrin: RED NIGHT (255 photos)",
        "[bluecake]-lee-ahrin-red-night")


def test_match_number_separator_variants():
    """"no.5988" / "no 5988" / "no5988" / 目录名前缀都必须等价。"""
    assert titles_match(
        "精选街拍作品 NO.5988 土豆丝裸腿美足特写[192P／307MB]",
        "未分类-261008a60008-精选街拍作品-no-5988-土豆丝裸腿美足特写[192p／307mb]")


def test_match_colon_vs_dash_separator():
    assert titles_match(
        "[JP] Chiyori Nakanishi (中西智代梨): 1st写真集「ちより日和」 (131 photos)  -",
        "[JP] Chiyori Nakanishi (中西智代梨) - 1st写真集「ちより日和」")


# ---- 负例:不同写真 -------------------------------------------------------------

def test_no_match_same_model_different_theme():
    assert not titles_match(
        "YeonYu (연유): Blue (101 photos + 6 videos)",
        "YeonYu (연유): Butterfly (122 photos)")
    assert not titles_match(
        "YeonYu (연유): Blue (101 photos + 6 videos)",
        "YeonYu (연유): Duisburg (63 photos)")


def test_no_match_same_model_different_album():
    assert not titles_match(
        "Suji (수지): Eat The Delivery Man (63 photos)",
        "Suji (수지): Wet Flight Attendant (106 photos)")


def test_no_match_same_publisher_different_model():
    assert not titles_match(
        "XIUREN No.962: Model Xiao Reba (小热巴) (44 photos)",
        "XIUREN No.6282 Daji_Toxic (妲己_Toxic) (44 photos)")


def test_no_match_same_series_different_issue():
    assert not titles_match(
        "ag-627 yeonyu yeon-yu (100 photos)",
        "YeonYu (연유): Blue (101 photos + 6 videos)")
    assert not titles_match(
        "ag627 yeonyu yeon-yu (100 photos)",
        "ag674 yeonyu yeon-yu (148 photos + 6 videos)")


def test_no_match_different_publisher_same_model_name():
    assert not titles_match(
        "YouMi Vol.922 Daji_Toxic (妲己_Toxic)",
        "XIUREN No.6282 Daji_Toxic (妲己_Toxic)")


def test_no_match_same_series_number_different_model():
    assert not titles_match(
        "XIUREN No.3128 Yang Chen Chen (杨晨晨sugar) (55 photos)",
        "XIUREN No.6282 Daji_Toxic (妲己_Toxic) (71 photos)")


def test_no_match_bare_model_name():
    """只有模特名(写真标题都算不上)不算写真级匹配。"""
    assert not titles_match("Suji (수지)",
                            "Suji (수지): Wet Flight Attendant (106 photos)")


def test_no_match_unrelated():
    assert not titles_match(
        "[JP] Chiyori Nakanishi (中西智代梨): 1st写真集「ちより日和」 (131 photos)  -",
        "[JP] Kawamichi Sara (川道さら) - 虹色シャワー PARADEデジタルフォトブック")
    assert not titles_match("[LE] LERB-002A G.su (55 photos)",
                            "[JP] Kasui Jun (香水じゅん) - Nude Photo Collection 写真集 Curves")


# ---- 边界 ---------------------------------------------------------------------

def test_tokens_drop_count_size_suffix():
    """张数/体积后缀必须整块剥掉, 不留数字残渣。"""
    assert title_tokens("精选街拍作品 NO.5988 土豆丝裸腿美足特写[192P／307MB]") == \
        ["精选街拍作品", "no5988", "土豆丝裸腿美足特写"]
    assert title_tokens("YeonYu (연유) - Blue [101P + 6V／585.6MB]") == \
        ["yeonyu", "연유", "blue"]


def test_tokens_dedup_repeated_name():
    """源站目录名把拼音名写两遍("yeonyu yeonyu"),token 不去重也能靠
    子序列包含匹配 —— 这里只断言两遍都在, 由 titles_match 负责等价。"""
    assert title_tokens("yeonyu yeonyu (연유) blue") == \
        ["yeonyu", "yeonyu", "연유", "blue"]


def test_empty_inputs_never_match():
    assert not titles_match("", "")
    assert not titles_match(None, "Blue")
    assert not titles_match("Blue", None)
