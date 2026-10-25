"""从写真标题抽取模特名 — 规则级联(移植自 docs/model-name/extract_models.py 原型)。

4kup.net 的 tag 只有分类(地区/出品方),模特名只存在于标题里,且高度
模板化(2026-10 实测 200 条规则命中 95%+,未命中的基本是真无人名系列,
如 GMS / BLT MONSTER / 杂志期号)。原型的别名字典与 LLM 兜底层依赖批量
语料与外部服务,采集 worker 是单条流水线,只移植零依赖的规则层。

用法: model_name_from_title("[JP] Toyoda Runa (豊田ルナ) 週刊少年…")
  → ("Toyoda Runa", "豊田ルナ");无人名返回 ("", "")。
"""

from __future__ import annotations

import re
from collections import Counter

# 不是人名的「名字位」占位符 / 系列名
_STOP = {
    "gms", "model collection", "model", "collection", "unknown",
    "ai enhanced", "ai", "photoset", "photobook", "gravure",
}

# 出现这些词说明已进入「作品名」部分,不是人名
_MARKERS = (
    "写真集", "デジタル", "グラビア", "Photo", "BOOKS", "Vol.", "Vol ",
    "No.", "1st", "2nd", "【", "「", "『", "SPA", "週刊", "MOCA",
)

# 番号: [LE] LEHC-037 / AG.737 / GMS-006A —— 名字位前跳过
_CODE_RE = re.compile(r"^[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?$")


def _clean(s: str) -> str:
    s = s.strip(" -–—|:：")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(?:DJAWA\s+Photo|Photo)\s+", "", s, flags=re.I)
    return s.strip()


def _valid(s: str) -> bool:
    if not s or len(s) > 40 or len(s) < 2:
        return False
    if s.lower() in _STOP:
        return False
    # 含数字且不含 CJK(末夜787 这类 CJK 名允许)
    if re.search(r"\d", s) and not re.search(r"[\u3400-\u9fff\uac00-\ud7af]", s):
        return False
    if any(m in s for m in _MARKERS):
        return False
    return bool(re.search(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", s))


def _valid_native(s: str) -> bool:
    if not s or len(s) > 30:
        return False
    if any(m in s for m in ("BOOKS", "PHOTO", "写真集", "デジタル", "Vol", "No.")):
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", s))


def _pair(rest: str) -> tuple[str, str] | None:
    """「Romanized (Native)」段 → (name, native);不匹配返回 None。"""
    m = re.match(r"(.{2,40}?)\s*\(([^)]{1,30})\)", rest)
    if m and _valid(_clean(m.group(1))) and _valid_native(m.group(2)):
        return _clean(m.group(1)), m.group(2).strip()
    return None


def model_name_from_title(title: str,
                          coser_bigrams: Counter | None = None) -> tuple[str, str]:
    """标题 → (模特名, 原生名)。无人名/低置信返回 ("", "")。

    规则按信号强度级联(强规则先跑),顺序敏感 —— 与原型实测 95%+
    命中的级联一致。
    """
    t = re.sub(r"\s+", " ", title or "").strip()
    if not t:
        return "", ""

    # 1) Coser@名字(Coser 帖名字位固定在 @ 后;两段式拉丁名靠共现判定)
    m = re.match(r"^(?:Coser|Cosplay)@\s*(.+)$", t)
    if m:
        toks = m.group(1).split()
        if toks:
            cand = toks[0]
            if (coser_bigrams and len(toks) >= 2
                    and re.fullmatch(r"[A-Z][A-Za-z.'\-]*", toks[0])
                    and re.fullmatch(r"[A-Z][A-Za-z.'\-]*", toks[1])
                    and coser_bigrams[f"{toks[0]} {toks[1]}"] >= 2):
                cand = f"{toks[0]} {toks[1]}"
            if _valid(cand):
                return cand, ""

    # 2) [内购无水印] 名字 秀人网模特 ... / 无标记时取首个中文名
    m = re.match(r"^\[内购无水印\]\s*(.+)$", t)
    if m:
        rest = m.group(1)
        mm = re.match(r"(.+?)\s+秀人网模特\b", rest)
        if mm and _valid(mm.group(1)):
            name = mm.group(1)
            p = _pair(name)
            if p:
                return p
            return name, ""
        first = rest.split()[0] if rest.split() else ""
        if re.search(r"[\u3400-\u9fff]", first) and _valid(first):
            return first, ""
        p = _pair(rest)
        if p:
            return p

    # 3) [AIGirl] 名字 0916(尾缀日期可无)
    m = re.match(r"^\[Ai?Girl\]\s*(.+)$", t, re.I)
    if m:
        rest = re.sub(r"\s+\d{3,4}[A-Z]?$", "", m.group(1)).strip()
        cand = rest if len(rest.split()) == 1 else rest.split()[0]
        if _valid(cand):
            return cand, ""

    # 4) [AI Enhanced] AG.737 YeonYu (연유)
    m = re.match(r"^\[AI Enhanced\]\s*[A-Z]{1,4}[._-]?\d{2,4}\s+(.+)$", t, re.I)
    if m:
        p = _pair(m.group(1).strip())
        if p:
            return p
        toks = m.group(1).split()
        if toks and _valid(toks[0]):
            return toks[0], ""

    # 5) [XR Uncensored] 名字 R18 秀人网模特 ...
    m = re.match(r"^\[XR Uncensored\]\s*(.+?)\s+(?:R18\s+)?秀人网模特\b", t, re.I)
    if m and _valid(m.group(1)):
        return m.group(1), ""

    # 6) DJAWA Photo 名字 (Native) – ...
    m = re.match(r"^DJAWA\s+Photo\s+(.+?)\s*(?:\(|–|-|$)", t, re.I)
    if m and _valid(_clean(m.group(1))):
        return _clean(m.group(1)), ""

    # 7) [地区] 番号 名字 (原生名) —— 全站最强通用信号,番号跳过
    m = re.match(
        r"^(?:\[[^\]]{1,20}\]\s*)?"
        r"(?:[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?\s+)?"
        r"(.{2,40}?)\s*\(([^)]{1,30})\)",
        t,
    )
    if m:
        p = _pair(f"{_clean(m.group(1))} ({m.group(2)})")
        if p:
            return p

    # 8) [LE] CODE 名字(名字位紧随番号后)
    m = re.match(r"^\[LE\]\s*[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?\s+([^\s(]+)", t)
    if m and _valid(m.group(1)):
        return m.group(1), ""

    # 9) [BLUECAKE] 名字 ...
    m = re.match(r"^\[BLUECAKE\]\s+(.+)$", t, re.I)
    if m:
        toks = m.group(1).split()
        cand = (" ".join(toks[:2])
                if len(toks) >= 2 and all(x[:1].isupper() for x in toks[:2])
                else toks[0])
        if _valid(cand):
            return cand, ""

    # 10) XIUREN / UGIRLS / IMISS / YouMi:编号后面就是名字
    for pat in (
        r"^XIUREN\s+No\.?\s*\d+\s+(.+)$",
        r"^UGIRLS(?:\s+App)?\s+No\.?\s*\d+\s+(.+)$",
        r"^IMISS\s+Vol\.?\s*\d+\s+(.+)$",
        r"^YouMi\s+Vol\.?\s*\d+\s+(.+)$",
    ):
        m = re.match(pat, t, re.I)
        if not m:
            continue
        rest = m.group(1).strip()
        p = _pair(rest)
        if p:
            return p
        cand = rest.split()[0] if rest.split() else ""
        if _valid(cand):
            return cand, ""
        return "", ""

    # 10b) 通用「系列 编号 名字」: MFStar Vol.190 程程CC /
    #      BoLoli Bol.054 Liu You Qi Sevenbaby (柳侑绮Sevenbaby)
    #      —— 4kup 老帖的主力形态(2021 及更早)。系列名本身不是人名,
    #      名字位固定在编号之后;以前 MFStar / BoLoli 不在上面那份白名单里,
    #      整批老帖落「未分类」(2026-10-24 任务 825 实录)。
    #      也吃「系列 U258 …」(UGirls 的写法)与「系列 日期 Vol.007 …」
    #      (HuaYang 的写法),日期只允许出现在系列名与编号之间。
    m = re.match(
        r"^[A-Za-z][A-Za-z0-9]{2,14}[\s._-]+"
        r"(?:\d{4}[-._/]\d{1,2}[-._/]\d{1,2}[\s._-]+)?"
        r"(?:Vol|No|Bol|U)\.?[\s._-]*\d{1,5}[\s._-]+(.+)$",
        t, re.I)
    if m:
        rest = m.group(1).strip()
        p = _pair(rest)
        if p:
            return p
        cand = rest.split()[0] if rest.split() else ""
        if _valid(cand):
            return cand, ""
        return "", ""

    # 11) [JP] 纯 CJK 名 + 作品标记
    m = re.match(
        r"^\[(?:JP|KR|CN|TW|HK)\]\s*"
        r"([\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af][^\s]{1,20})\s+"
        r"(?=「|『|【|写真集|デジタル|グラビア|Vol|SPA|FRIDAY|DOLCE|Platinum|"
        r"FLASH|週刊|BRODY|JUICY|1st|2nd)",
        t,
    )
    if m and _valid(m.group(1)):
        return m.group(1), ""

    # 12) [JP]/[KR] 拉丁名 + 作品标记
    m = re.match(
        r"^\[(?:JP|KR|CN|TW|HK|AI Enhanced)\]\s*"
        r"([A-Z][\w.'\-]*(?:\s+[A-Z][\w.'\-]*){0,2})\s+"
        r"(?=写真集|デジタル|1st|2nd|【|「|『|\(|SPA|週刊|EX|MOCA|グラビア|Photo|Vol)",
        t,
    )
    if m and _valid(m.group(1)):
        return m.group(1), ""

    return "", ""

