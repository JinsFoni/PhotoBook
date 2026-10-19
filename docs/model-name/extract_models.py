#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_models.py — 从 4kup.net 的写真标题中抽取模特名（原型）

思路：规则优先 → 别名字典兜底 → 低置信度留给人工/LLM 复核。

用法：
    python3 extract_models.py --pages 10 --out models.csv
    python3 extract_models.py --pages 3 --show-unmatched 30
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

API = "https://4kup.net/wp-json/wp/v2/posts"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"

# 不是人名的“名字位”占位符 / 系列名
STOP = {
    "gms", "model collection", "model", "collection", "unknown",
    "ai enhanced", "ai", "photoset", "photobook", "gravure",
}

# 出现这些词说明已经进入“作品名”部分，不是人名
MARKERS = (
    "写真集", "デジタル", "グラビア", "Photo", "BOOKS", "Vol.", "Vol ",
    "No.", "1st", "2nd", "【", "「", "『", "SPA", "週刊", "MOCA",
)

CODE_RE = re.compile(r"^[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?$")


# --------------------------------------------------------------------------- #
# 抓取
# --------------------------------------------------------------------------- #
def fetch_titles(pages: int, per_page: int = 100) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, pages + 1):
        qs = urllib.parse.urlencode({
            "per_page": per_page,
            "page": page,
            "_fields": "id,date,link,title,categories",
        })
        batch = None
        for attempt in range(3):
            req = urllib.request.Request(f"{API}?{qs}", headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as exc:  # noqa: BLE001
                print(f"! page {page} 第 {attempt+1} 次失败: {exc}", file=sys.stderr)
                time.sleep(1.5 * (attempt + 1))
        if batch is None:
            break
        if not batch:
            break
        for p in batch:
            rows.append({
                "id": p["id"],
                "date": p.get("date", "")[:10],
                "link": p.get("link", ""),
                "title": html.unescape(p["title"]["rendered"]).strip(),
            })
        print(f"  page {page}: +{len(batch)} (total {len(rows)})", file=sys.stderr)
        time.sleep(0.3)
    return rows


# --------------------------------------------------------------------------- #
# 清洗 / 校验
# --------------------------------------------------------------------------- #
def norm(s: str) -> str:
    return re.sub(r"[\s._\-·]+", "", s).lower()


def clean_name(s: str) -> str:
    s = s.strip(" -–—|:：")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(?:DJAWA\s+Photo|Photo)\s+", "", s, flags=re.I)
    return s.strip()


def valid_name(s: str) -> bool:
    if not s or len(s) > 40 or len(s) < 2:
        return False
    if s.lower() in STOP:
        return False
    if re.search(r"\d", s) and not re.search(r"[\u3400-\u9fff\uac00-\ud7af]", s):
        return False
    if any(m in s for m in MARKERS):
        return False
    # 至少要有字母或 CJK
    if not re.search(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", s):
        return False
    return True


def valid_native(s: str) -> bool:
    if not s or len(s) > 30:
        return False
    if any(m in s for m in ("BOOKS", "PHOTO", "写真集", "デジタル", "Vol", "No.")):
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", s))


# --------------------------------------------------------------------------- #
# 规则抽取
# --------------------------------------------------------------------------- #
def rule_extract(title: str, coser_bigrams: Counter | None = None) -> dict | None:
    t = re.sub(r"\s+", " ", title).strip()

    # 1) Coser@名字（两段式拉丁名靠语料共现判定，如 Messie Huang / Hatori Sama）
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
            if valid_name(cand):
                return {"model": cand, "native": "", "method": "coser", "conf": 0.95}

    # 2) [内购无水印] 名字 秀人网模特 ... / 无标记时取首个中文名
    m = re.match(r"^\[内购无水印\]\s*(.+)$", t)
    if m:
        rest = m.group(1)
        mm = re.match(r"(.+?)\s+秀人网模特\b", rest)
        if mm and valid_name(mm.group(1)):
            name = mm.group(1)
            mn = re.match(r"(.+?)\s*\(([^)]{1,30})\)", name)
            if mn and valid_name(mn.group(1)) and valid_native(mn.group(2)):
                return {"model": mn.group(1), "native": mn.group(2),
                        "method": "neigou", "conf": 0.95}
            return {"model": name, "native": "", "method": "neigou", "conf": 0.95}
        first = rest.split()[0]
        if re.search(r"[\u3400-\u9fff]", first) and valid_name(first):
            return {"model": first, "native": "", "method": "neigou", "conf": 0.85}
        mp = re.match(r"(.{2,40}?)\s*\(", rest)
        if mp and valid_name(mp.group(1)):
            return {"model": mp.group(1), "native": "", "method": "neigou", "conf": 0.8}

    # 2.5) [AIGirl] 名字 0916 / 0903B（也兼容无日期）
    m = re.match(r"^\[Ai?Girl\]\s*(.+)$", t, re.I)
    if m:
        rest = re.sub(r"\s+\d{3,4}[A-Z]?$", "", m.group(1)).strip()
        cand = rest if len(rest.split()) == 1 else rest.split()[0]
        if valid_name(cand):
            return {"model": cand, "native": "", "method": "aigirl", "conf": 0.9}

    # 2.55) [AI Enhanced] AG.737 YeonYu (연유) / AG.765 YeonJju
    m = re.match(r"^\[AI Enhanced\]\s*AG\.\d+\s+(.+)$", t, re.I)
    if m:
        rest = m.group(1).strip()
        mp = re.match(r"(.{2,40}?)\s*\(([^)]{1,30})\)", rest)
        if mp and valid_name(mp.group(1)):
            return {"model": mp.group(1), "native": mp.group(2), "method": "ag", "conf": 0.9}
        cand = rest.split()[0]
        if valid_name(cand):
            return {"model": cand, "native": "", "method": "ag", "conf": 0.8}

    # 2.6) [XR Uncensored] 名字 R18 秀人网模特 ...
    m = re.match(r"^\[XR Uncensored\]\s*(.+?)\s+(?:R18\s+)?秀人网模特\b", t, re.I)
    if m and valid_name(m.group(1)):
        return {"model": m.group(1), "native": "", "method": "xr", "conf": 0.9}

    # 3) DJAWA Photo 名字 (Native) ...
    m = re.match(r"^DJAWA\s+Photo\s+(.+?)\s*(?:\(|–|-|$)", t, re.I)
    if m and valid_name(clean_name(m.group(1))):
        return {"model": clean_name(m.group(1)), "native": "", "method": "dajawa", "conf": 0.8}

    # 4) 带原生名的 “Romanized (Native)” —— 本网站最强的信号
    m = re.match(
        r"^(?:\[[^\]]{1,20}\]\s*)?"
        r"(?:[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?\s+)?"
        r"(.{2,40}?)\s*\(([^)]{1,30})\)",
        t,
    )
    if m:
        name, native = clean_name(m.group(1)), m.group(2).strip()
        if valid_name(name) and valid_native(native):
            return {"model": name, "native": native, "method": "pair", "conf": 0.9}

    # 5) [LE] CODE 名字
    m = re.match(r"^\[LE\]\s*[A-Z]{2,6}[._-]?\d{2,4}[A-Z]?\s+([^\s(]+)", t)
    if m and valid_name(m.group(1)):
        return {"model": m.group(1), "native": "", "method": "le", "conf": 0.75}

    # 6) [BLUECAKE] 名字 ...
    m = re.match(r"^\[BLUECAKE\]\s+(.+)$", t, re.I)
    if m:
        toks = m.group(1).split()
        cand = " ".join(toks[:2]) if len(toks) >= 2 and all(x[:1].isupper() for x in toks[:2]) else toks[0]
        if valid_name(cand):
            return {"model": cand, "native": "", "method": "bluecake", "conf": 0.6}

    # 7) XIUREN / UGIRLS / IMISS：编号后面就是名字
    for pat, method in (
        (r"^XIUREN\s+No\.?\s*\d+\s+(.+)$", "xiuren"),
        (r"^UGIRLS(?:\s+App)?\s+No\.?\s*\d+\s+(.+)$", "ugirls"),
        (r"^IMISS\s+Vol\.?\s*\d+\s+(.+)$", "imiss"),
        (r"^YouMi\s+Vol\.?\s*\d+\s+(.+)$", "youmi"),
    ):
        m = re.match(pat, t, re.I)
        if not m:
            continue
        rest = m.group(1).strip()
        mp = re.match(r"(.{2,40}?)\s*\(([^)]{1,30})\)", rest)
        if mp and valid_name(clean_name(mp.group(1))):
            return {"model": clean_name(mp.group(1)), "native": mp.group(2),
                    "method": method, "conf": 0.9}
        cand = rest.split()[0] if rest.split() else ""
        if valid_name(cand):
            return {"model": cand, "native": "", "method": method, "conf": 0.8}
        return None

    # 8) [JP] 纯日文名 + 作品标记（山田あい / 福井梨莉華 …）
    m = re.match(
        r"^\[(?:JP|KR|CN|TW|HK)\]\s*"
        r"([\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af][^\s]{1,20})\s+"
        r"(?=「|『|【|写真集|デジタル|グラビア|Vol|SPA|FRIDAY|DOLCE|Platinum|FLASH|週刊|BRODY|JUICY|1st|2nd)",
        t,
    )
    if m and valid_name(m.group(1)):
        return {"model": m.group(1), "native": "", "method": "bracket_cjk", "conf": 0.75}

    # 9) [JP]/[KR] 无括号：名字 + 作品标记
    m = re.match(
        r"^\[(?:JP|KR|CN|TW|HK|AI Enhanced)\]\s*"
        r"([A-Z][\w.'\-]*(?:\s+[A-Z][\w.'\-]*){0,2})\s+"
        r"(?=写真集|デジタル|1st|2nd|【|「|『|\(|SPA|週刊|EX|MOCA|グラビア|Photo|Vol)",
        t,
    )
    if m and valid_name(m.group(1)):
        return {"model": m.group(1), "native": "", "method": "bracket", "conf": 0.75}

    return None


# --------------------------------------------------------------------------- #
# 别名字典
# --------------------------------------------------------------------------- #
def build_aliases(rows: list[dict]) -> dict[str, dict]:
    """从高置信度结果里建 别名 -> 规范名 的映射。"""
    aliases: dict[str, dict] = {}
    for r in rows:
        hit = r.get("hit")
        if not hit or hit["conf"] < 0.8:
            continue
        canonical = hit["model"]
        for key in {hit["model"], hit.get("native", "")}:
            k = norm(key)
            if len(k) >= 3 and k not in aliases:
                aliases[k] = {"model": canonical, "native": hit.get("native", ""),
                              "raw": key}
    return aliases


def dict_extract(title: str, aliases: dict[str, dict]) -> dict | None:
    nt = norm(title)
    tl = re.sub(r"\s+", " ", title.lower())
    best = None
    for k, v in aliases.items():
        if len(k) < 3:
            continue
        raw = v.get("raw", k)
        if re.fullmatch(r"[a-z0-9 ._\-']+", raw.lower()):
            # 拉丁别名：在保留空格的原文上做词边界匹配，避免 Ray 命中 Stray
            pat = r"(?<![a-z0-9])" + re.escape(raw.lower()).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
            if not re.search(pat, tl):
                continue
        else:
            if k not in nt:
                continue
        if best is None or len(k) > len(best[0]):
            best = (k, v)
    if not best:
        return None
    return {"model": best[1]["model"], "native": best[1].get("native", ""),
            "method": "dict", "conf": 0.6}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=10, help="抓取页数，每页 100 条")
    ap.add_argument("--out", default="", help="输出 CSV 路径")
    ap.add_argument("--show-unmatched", type=int, default=15)
    args = ap.parse_args()

    print("抓取标题…", file=sys.stderr)
    rows = fetch_titles(args.pages)
    if not rows:
        print("没有抓到数据。", file=sys.stderr)
        return 1

    coser_bigrams = Counter()
    for r in rows:
        m = re.match(r"^(?:Coser|Cosplay)@\s*(\S+)\s+(\S+)", r["title"])
        if m and re.fullmatch(r"[A-Z][A-Za-z.'\-]*", m.group(1)) and re.fullmatch(r"[A-Z][A-Za-z.'\-]*", m.group(2)):
            coser_bigrams[f"{m.group(1)} {m.group(2)}"] += 1

    for r in rows:
        r["hit"] = rule_extract(r["title"], coser_bigrams)

    aliases = build_aliases(rows)
    for r in rows:
        if not r["hit"]:
            r["hit"] = dict_extract(r["title"], aliases)

    matched = [r for r in rows if r["hit"]]
    unmatched = [r for r in rows if not r["hit"]]

    print(f"\n总计 {len(rows)} 条，命中 {len(matched)} 条 "
          f"({len(matched) * 100 / len(rows):.1f}%)，未命中 {len(unmatched)} 条")
    print("\n按方法：")
    for k, v in Counter(r["hit"]["method"] for r in matched).most_common():
        print(f"  {k:10s} {v}")
    print("\n出现最多的模特：")
    for name, cnt in Counter(r["hit"]["model"] for r in matched).most_common(15):
        print(f"  {cnt:4d}  {name}")

    if args.show_unmatched:
        print(f"\n未命中示例（前 {args.show_unmatched} 条）：")
        for r in unmatched[: args.show_unmatched]:
            print("  -", r["title"][:100])

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["date", "model", "native", "method", "confidence", "title", "link"])
            for r in rows:
                h = r["hit"] or {}
                w.writerow([r["date"], h.get("model", ""), h.get("native", ""),
                            h.get("method", ""), h.get("conf", ""), r["title"], r["link"]])
        print(f"\n已写入 {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
