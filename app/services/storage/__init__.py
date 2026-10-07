"""外部存储上传服务。"""

from __future__ import annotations

import logging

from sqlalchemy import select

from ...db import Photo, PhotoUpload, Storage

log = logging.getLogger("pb.storage")


def remote_redirect(rel: str) -> str | None:
    """本地缺失的原图在任一启用存储上的公开 URL(serve_media 302 用)。

    rel 是 /media 相对路径(如 "chunmomo/xxx/001.jpg");photo_uploads 按
    photo_id 关联,先反查 Photo。找不到返回 None(保持 404 行为)。
    """
    from ...database import SessionLocal

    s = SessionLocal()
    try:
        photo_id = s.scalar(select(Photo.id).where(Photo.filename == rel))
        if photo_id is None:
            return None
        row = s.execute(
            select(PhotoUpload.remote_path, Storage)
            .join(Storage, Storage.id == PhotoUpload.storage_id)
            .where(PhotoUpload.photo_id == photo_id, Storage.enabled == True)  # noqa: E712
            .limit(1)).first()
        if not row:
            return None
        remote_path, st = row
        from .base import get_backend
        try:
            return get_backend(st).public_url(st, remote_path)
        except Exception:
            log.exception("public_url failed: storage %s", st.id)
            return None
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