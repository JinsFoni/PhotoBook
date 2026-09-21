"""harvest.filters — 标题/标签黑白名单、模特名挑选、路径清洗。"""

from __future__ import annotations

import pytest

from app.services.harvest.filters import (DEFAULT_MODEL_EXCLUDE, check_title, keyword_hit,
                                          matches_any, normalize_key, pick_model_name,
                                          sanitize_path_part)


def test_no_filters_allows_all():
    assert check_title("任何标题", None, None).allowed


def test_blacklist_rejects():
    r = check_title("School Nurse Vol.2", None, "nurse")
    assert not r.allowed and r.keyword == "nurse"


def test_blacklist_case_insensitive():
    assert not check_title("SUMMER Beach", None, "beach").allowed


def test_whitelist_requires_match():
    assert check_title("Summer Beach", "summer,beach", "").allowed
    r = check_title("Winter Trip", "summer", "")
    assert not r.allowed


def test_blacklist_beats_whitelist():
    assert not check_title("Summer Nurse", "summer", "nurse").allowed


def test_newline_separated_keywords():
    assert not check_title("Yeha Nurse", "yeha\nschool", "nurse").allowed


def test_sanitize_path_part():
    assert sanitize_path_part("a/b:c*d") == "a-b-c-d"
    assert sanitize_path_part("..hidden.") == "hidden"
    assert sanitize_path_part("") == "untitled"
    assert sanitize_path_part("正常标题 123") == "正常标题 123"


def test_sanitize_blocks_traversal():
    part = sanitize_path_part("../../etc")
    assert "/" not in part and ".." not in part


# ---- 黑名单看标签 ---------------------------------------------------------

def test_blacklist_matches_tags():
    """黑名单:标题或标签命中即跳过(用户定义)。"""
    r = check_title("School Nurse Vol.2", None, "nurse", tags=["Cosplay"])
    assert not r.allowed and r.keyword == "nurse"
    r = check_title("写真集 A", None, "jav", tags=["Cosplay", "JAV"])
    assert not r.allowed and r.keyword == "jav"
    assert check_title("写真集 A", None, "jav", tags=["Cosplay"]).allowed


def test_whitelist_sees_tags_too():
    assert check_title("Untitled", "cosplay", "", tags=["Cosplay"]).allowed
    assert not check_title("Untitled", "cosplay", "", tags=["Nurse"]).allowed


# ---- 按词匹配(模特名排除词) --------------------------------------------

def test_normalize_key():
    assert normalize_key("AI-Generated_01") == "ai generated 01"
    assert normalize_key("内购无水印") == "内购无水印"
    assert normalize_key(None) == ""


def test_keyword_hit_word_boundary():
    # 短词不会误伤长词
    assert keyword_hit("jp 11853", "jp")
    assert not keyword_hit("magda 123", "ag")
    assert not keyword_hit("magdalena", "ag")
    assert keyword_hit("ag 11787", "ag")
    assert keyword_hit("AI Generated", "ai generated")
    assert not keyword_hit("AI", "ai generated")
    # 中文关键词照旧子串命中
    assert keyword_hit("内购无水印 14442", "内购无水印")
    assert keyword_hit("NS纳丝摄影 3312", "ns纳丝摄影")


def test_matches_any_returns_keyword():
    assert matches_any("Cosplay 12", DEFAULT_MODEL_EXCLUDE) == "cosplay"
    assert matches_any("Yeha", DEFAULT_MODEL_EXCLUDE) == ""


def test_pick_model_name():
    # 出品方/分类 tag 总在前面 → 取第一个未被排除的
    assert pick_model_name(["Cosplay", "麻花麻花酱"]) == "麻花麻花酱"
    assert pick_model_name(["JP", "ATFM", "Tsubaki"]) == "Tsubaki"
    assert pick_model_name(["Yeha", "AI Enhanced"]) == "Yeha"
    # 全被排除 / 无标签 → 空(调用方落到「未分类」)
    assert pick_model_name(["AI Generated"]) == ""
    assert pick_model_name([]) == ""
    assert pick_model_name(None) == ""
    # 自定义排除词
    assert pick_model_name(["Yeha", "Cosplay"], exclude="yeha") == "Cosplay"


def test_pick_model_name_skips_junk_tags():
    assert pick_model_name(["(42 photos)", "Yeha"]) == "Yeha"
    assert pick_model_name(["  ", "...", "!!!!"]) == ""
    assert pick_model_name(["Graphis", "Yeha"]) == "Yeha"
