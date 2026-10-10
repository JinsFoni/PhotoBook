"""外部存储上传服务。"""

from __future__ import annotations

import logging

from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ...db import Photo, PhotoUpload, Storage

log = logging.getLogger("pb.storage")

# 远端文件按扩展名映射响应类型(存储端返回的 Content-Type 不可靠)
_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".avif": "image/avif",
}


def remote_stream(url: str, request_headers: dict[str, str] | None = None) -> StreamingResponse | None:
    """服务端流式代理远端原图(本地缺失时的回源,serve_media 用)。

    流式透传不落盘:上游字节直接转发给客户端,内存占用恒定,18MB 原图
    与 1MB 行为一致。Range 头透传(下载续传/拖动进度条),上游 206 原样
    回 206;高优先级存储不可达返回 None,调用方落到下一级。

    同步 httpx 迭代器交给 Starlette 线程池泵(serve_media 本就是同步 def,
    与缩略图回源同一并发闸门约束)。"""
    import httpx

    try:
        timeout = httpx.Timeout(120.0, connect=15.0)
        client = httpx.Client(timeout=timeout, follow_redirects=True)
        headers = {k: v for k, v in (request_headers or {}).items()
                   if k.lower() == "range"}
        req = client.build_request("GET", url, headers=headers)
        resp = client.send(req, stream=True)
        if resp.status_code not in (200, 206):
            resp.close()
            client.close()
            return None
        media_type = (_MIME_BY_EXT.get(_ext_of(url))
                      or resp.headers.get("content-type", "image/jpeg"))
        out_headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        if "content-length" in resp.headers:
            out_headers["Content-Length"] = resp.headers["content-length"]
        if "accept-ranges" in resp.headers:
            out_headers["Accept-Ranges"] = resp.headers["accept-ranges"]
        return StreamingResponse(
            _iter_and_close(client, resp),
            status_code=resp.status_code,
            media_type=media_type, headers=out_headers,
        )
    except Exception:
        log.warning("remote stream failed: %s", url[:120], exc_info=True)
        return None


def _ext_of(url: str) -> str:
    from pathlib import PurePosixPath
    path = url.split("?", 1)[0].split("#", 1)[0]
    return PurePosixPath(path).suffix.lower()


def _iter_and_close(client: "httpx.Client", resp: "httpx.Response"):
    """上游字节逐块透传;生成器被消费完(或客户端中断触发 GeneratorExit)
    时关闭上游连接,不留悬挂 socket。"""
    try:
        for chunk in resp.iter_bytes(64 * 1024):
            yield chunk
    finally:
        resp.close()
        client.close()


def remote_urls(rel: str) -> list[str]:
    """开启直链的启用存储的公开 URL,按优先级从高到低(优先级相同按存储 id 新者优先)。

    本地原图缺失时的回源地址:serve_media 流式代理与 serve_thumb 回源生成
    都按此顺序尝试,高优先级失败自动落到下一级。direct_link 关闭的存储是
    纯备份,不参与回源。
    """
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        photo_id = s.scalar(select(Photo.id).where(Photo.filename == rel))
        if photo_id is None:
            return []
        rows = s.execute(
            select(PhotoUpload.remote_path, Storage)
            .join(Storage, Storage.id == PhotoUpload.storage_id)
            .where(PhotoUpload.photo_id == photo_id, Storage.enabled == True,  # noqa: E712
                   Storage.direct_link == True)  # noqa: E712
            .order_by(Storage.priority.desc(), Storage.id.desc())).all()
        urls: list[str] = []
        for remote_path, st in rows:
            from .base import get_backend
            try:
                urls.append(get_backend(st).public_url(st, remote_path))
            except Exception:
                log.exception("public_url failed: storage %s", st.id)
        return urls
    finally:
        s.close()


def purge_remote_of_collection(collection_id: int) -> None:
    """删除写真集时同步清理远端文件(尽力而为,失败不阻断本地删除)。

    按 storage 分组调 delete_batch,然后删除 photo_uploads 记录。
    """
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        rows = s.execute(
            select(PhotoUpload.remote_path, PhotoUpload.storage_id)
            .join(Photo, Photo.id == PhotoUpload.photo_id)
            .where(Photo.collection_id == collection_id)).all()
        if not rows:
            return
        by_storage: dict[int, list[str]] = {}
        for remote_path, sid in rows:
            by_storage.setdefault(sid, []).append(remote_path)
        for sid, paths in by_storage.items():
            st = s.get(Storage, sid)
            if not st:
                continue
            try:
                from .base import get_backend
                get_backend(st).delete_batch(st, paths)
                log.info("purged %d remote files of collection %s from %s",
                         len(paths), collection_id, st.name)
            except Exception:
                log.exception("remote purge failed: collection %s storage %s"
                              " (%d files left behind)", collection_id, sid, len(paths))
        # 记录无论如何都删(DB 级联也会删,这里显式删保持一致)
        s.query(PhotoUpload).filter(
            PhotoUpload.photo_id.in_(
                select(Photo.id).where(Photo.collection_id == collection_id))
        ).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()