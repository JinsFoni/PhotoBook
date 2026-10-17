"""跨站标题比对 — titles_match 的判据(真实站点标题采样)。

三个源站对同一本写有的标题写法不同(buondua og:title / misskon h1 /
nicesss og:title),且同一站在不同期的写真标题高度相似。判据必须
同时做到:同作品跨站命中, 同模特不同作品、同系列不同期不误配。
"""

from __future__ import annotations

from app.services.harvest.titlematch import (photo_count, title_matches_collection,
                                             title_tokens, titles_match)


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


def test_no_match_same_title_different_photo_count():
    """泛化标题(系列名)不同批次的写真共用同一标题,只差张数 —— 张数不等
    必须判不是同一本(47799 ↔ 44755 误判实录: 25/121/310 张各一期全被
    吸进同一个 source_serials)。"""
    assert not titles_match(
        "[AI Generated] 诛仙 陆雪琪 (25 photos)  -",
        "[AI Generated] 诛仙-陆雪琪 (310 photos)")
    assert not titles_match(
        "[AI Generated] 诛仙-陆雪琪 (121 photos)  -",
        "[AI Generated] 诛仙-陆雪琪 (310 photos)")


def test_match_same_title_same_photo_count():
    """张数相等 + 文本等价 → 照常命中(跨站同本写真张数一致)。"""
    assert titles_match("[AI Generated] 诛仙-陆雪琪 (100 photos)",
                        "[AI Generated] 诛仙-陆雪琪")


def test_no_match_count_mismatch_overrides_text_match():
    """文本完全一致但张数不同 → 不匹配(守卫优先于子序列判定)。"""
    assert not titles_match("YeonYu (연유): Blue (101 photos)",
                            "YeonYu (연유): Blue (63 photos)")
    # nicesss P-记法 vs photos-记法,张数不等同样拦截
    assert not titles_match("YeonYu (연유) - Blue [101P／585.6MB]",
                            "YeonYu (연유): Blue (63 photos)")


def test_match_count_unknown_falls_back_to_text():
    """一侧张数解析不出(归档目录名/老帖标题)→ 退回纯文本判定。"""
    assert titles_match(
        "XIUREN No.6282: Daji_Toxic (妲己_Toxic) (71 photos) -",
        "XIUREN No.6282 Daji_Toxic (妲己_Toxic)")
    assert titles_match("YeonYu (연유): Blue (101 photos + 6 videos)  -",
                        "yeonyu yeonyu (연유) blue")


def test_photo_count_extracts_all_notations():
    """photos 记法与 nicesss P 记法都取得到;P+V 只算照片;无后缀 = None。"""
    assert photo_count("[AI Generated] 诛仙-陆雪琪 (310 photos)") == 310
    assert photo_count("YeonYu (연유): Blue (101 photos + 6 videos)  -") == 101
    assert photo_count("YeonYu (연유) - Blue [101P + 6V／585.6MB]") == 101
    assert photo_count("精选街拍作品 NO.5988 土豆丝裸腿美足特写[192P／307MB]") == 192
    assert photo_count("XIUREN No.6282 Daji_Toxic (妲己_Toxic)") is None
    assert photo_count("") is None
    assert photo_count(None) is None


# ---- title_matches_collection: 库侧真实张数守卫 ---------------------------------

def test_collection_guard_blocks_generic_series_title():
    """生产库 310/310 的 collection title 不带张数尾缀 —— titles_match 的
    双侧守卫对它单向失效,必须用 photos 表真实张数补上(44755 实录)。"""
    col_title = "[AI Generated] 诛仙-陆雪琪"     # 入库形态,无尾缀
    assert not title_matches_collection(
        "[AI Generated] 诛仙-陆雪琪 (310 photos)", col_title, 100)
    assert not title_matches_collection(
        "[AI Generated] 诛仙 陆雪琪 (25 photos)  -", col_title, 100)
    assert title_matches_collection(
        "[AI Generated] 诛仙-陆雪琪 (100 photos)", col_title, 100)


def test_collection_guard_unknown_count_falls_back():
    """真实张数未知(None)→ 退回纯文本判定,行为同旧版。"""
    col_title = "XIUREN No.6282 Daji_Toxic (妲己_Toxic)"
    assert title_matches_collection(
        "XIUREN No.6282: Daji_Toxic (妲己_Toxic) (71 photos) -", col_title, None)
    # 文本本来就不匹配 → 照旧 False
    assert not title_matches_collection(
        "XIUREN No.962 Xiao Reba (小热巴) (44 photos)", col_title, None)


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
