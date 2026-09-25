"""标签落库 — 采集管道解析到的 tag 写入并关联到合集与模特(M5 补课)。

此前详情页解析出的 target.tags 只用于黑白名单过滤和挑模特名,入库前被丢弃,
导致 tags 表永远为空、发现页「0 tags」。本模块提供唯一的打标入口:

- ``apply_tags(s, collection, model, tags)``:把显示名 tag 幂等写入 tags 表,
  同时挂到合集与模特(model_tags / collection_tags)
- ``retag_from_history(s)``:补录 —— 用 harvest_jobs 里已 done 任务的 url
  重新解析详情页,把 tag 补到已导入的合集/模特上(幂等,可重复跑)

tag 全部保留(含出品方/分类类),按用户 2026-09 决定:「都挂、都要、补旧数据」。
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Collection, CollectionTag, HarvestJob, Model, ModelTag, Tag
from .harvest import net

log = logging.getLogger("tagging")


def _get_or_create_tag(s: Session, name: str) -> Tag:
    slug = name.lower().replace(" ", "-")
    t = s.scalar(select(Tag).where(Tag.slug == slug))
    if not t:
        t = Tag(name=name[:80], slug=slug[:80])
        s.add(t)
        s.flush()
    return t


def apply_tags(s: Session, collection: Collection | None,
               model: Model | None, tags: list[str]) -> int:
    """把 tag 幂等挂到合集与模特。返回本次新关联数(用于日志/统计)。

    tag 记录全局共享(同一名字只建一次);合集与模特任一存在即挂,
    两个都传就都挂 —— 调用方不用关心拆分。
    """
    if not tags or (collection is None and model is None):
        return 0
    added = 0
    for name in tags:
        name = name.strip()
        if not name:
            continue
        t = _get_or_create_tag(s, name)
        if collection is not None and t not in collection.tags:
            collection.tags.append(t)
            added += 1
        if model is not None and t not in model.tags:
            model.tags.append(t)
            added += 1
    return added


def _norm_title(s: str) -> str:
    """标题归一化:去照片数后缀与站点尾巴,小写、去空白/标点。
    og:title 形如「Yeha (예하): School Nurse (219 photos) - BuonDua」,
    合集标题(库目录名)形如「Yeha (예하) - School Nurse」,直接比对不上。"""
    import re

    s = re.sub(r"\s*\(\s*\d+\s+photos?\s*\)\s*", " ", s or "")
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u3400-\u9fff\uff66-\uff9f]+", "",
                  s.lower())


def _find_collection(s: Session, job_title: str) -> Collection | None:
    """按归一化标题找合集:全等优先,其次包含匹配,取最长(最具体)者;
    同长多解视为有歧义,跳过。"""
    want = _norm_title(job_title)
    if not want:
        return None
    cols = s.scalars(select(Collection)).all()
    exact = [c for c in cols if _norm_title(c.title) == want]
    if len(exact) == 1:
        return exact[0]
    # 包含匹配:任务标题可能带照片数/站点尾巴,合集标题可能被截断
    cand = [(c, len(_norm_title(c.title))) for c in cols
            if _norm_title(c.title)
            and (_norm_title(c.title) in want or want in _norm_title(c.title))]
    if not cand:
        return None
    best = max(n for _c, n in cand)
    winners = [c for c, n in cand if n == best]
    return winners[0] if len(winners) == 1 else None


def retag_from_history(s: Session, *, limit: int | None = None) -> dict:
    """补录:重新解析已 done 采集任务的详情页,把 tag 补到已导入数据上。

    匹配链:harvest_jobs.url → 详情页 tags;任务按 title → job 匹配到合集
    (title 存的是 og:title,导入时合集 title = 库目录名,两者通常一致;
    对不上的记 skipped)。模特经合集的 model_id 顺带拿到,一并打标。
    幂等:重复跑只在有新关联时写入。返回统计 {matched, tagged, skipped}。
    """
    jobs = s.scalars(
        select(HarvestJob).where(HarvestJob.status == "done")
        .order_by(HarvestJob.id)).all()
    if limit:
        jobs = jobs[:limit]
    stats = {"matched": 0, "tagged": 0, "skipped": 0}
    for job in jobs:
        if not job.url:
            stats["skipped"] += 1
            continue
        title = (job.title or "").strip()
        if not title:
            stats["skipped"] += 1
            continue
        # title → 合集(归一化匹配,兼容 og:title 与目录名分隔符差异)
        c = _find_collection(s, title)
        if c is None:
            log.info("retag: 无合集匹配 %r", title)
            stats["skipped"] += 1
            continue
        try:
            html = net.fetch_html(job.url)
            target = net.parse_detail_page(job.url, existing_html=html)
        except Exception:
            log.exception("retag: 解析失败 %s", job.url)
            stats["skipped"] += 1
            continue
        if not target.tags:
            stats["skipped"] += 1
            continue
        stats["matched"] += 1
        stats["tagged"] += apply_tags(s, c, c.model, target.tags)
        s.commit()
    return stats
