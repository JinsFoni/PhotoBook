"""照片元数据管理 JSON API — 灯箱内「设为封面 / 设为模特头像」。

仅 admin(普通用户请求直接 403);前端按钮也已按角色隐藏,这里双保险。
封面/头像展示端(_collection_cover / _model_payload)都实时读库,改完即生效,
无需清缓存 —— 缩略图文件本身不变,变的只是指向哪张图。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import Collection, Photo, User
from ..database import get_db

router = APIRouter(prefix="/api/photo-meta")


class PhotoMetaIn(BaseModel):
    photo_id: int
    target: str  # cover | avatar


@router.post("")
async def set_photo_meta(body: PhotoMetaIn, user: User = Depends(require_admin),
                         s: Session = Depends(get_db)):
    if body.target not in ("cover", "avatar"):
        raise HTTPException(400, "bad target")
    ph = s.get(Photo, body.photo_id)
    if not ph:
        raise HTTPException(404, "photo not found")
    if body.target == "cover":
        c = s.get(Collection, ph.collection_id)
        if not c:
            raise HTTPException(404, "collection not found")
        c.cover_photo_id = ph.id
    else:
        c = s.get(Collection, ph.collection_id)
        m = c.model if c else None
        if not m:
            raise HTTPException(400, "collection has no model")  # 未归属模特,无处可设
        m.avatar_path = ph.filename
    s.commit()
    return {"ok": True, "target": body.target, "photo_id": body.photo_id}
