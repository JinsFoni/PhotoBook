"""收藏 JSON API — 登录后服务端存储,取代 localStorage。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import Favorite, User
from ..database import get_db

router = APIRouter(prefix="/api/favorites")


class FavIn(BaseModel):
    type: str            # model | collection | photo
    key: str             # slug 或 collection:idx
    added: bool


@router.get("")
async def list_favorites(user: User = Depends(require_login), s: Session = Depends(get_db)):
    rows = s.scalars(select(Favorite).where(Favorite.user_id == user.id)).all()
    out = {"model": [], "collection": [], "photo": []}
    for r in rows:
        if r.target_type in out:
            out[r.target_type].append(r.target_key)
    return out


@router.post("")
async def toggle_favorite(body: FavIn, user: User = Depends(require_login),
                          s: Session = Depends(get_db)):
    if body.type not in ("model", "collection", "photo"):
        raise HTTPException(400, "bad type")
    row = s.scalar(select(Favorite).where(
        Favorite.user_id == user.id, Favorite.target_type == body.type,
        Favorite.target_key == body.key))
    if body.added:
        if not row:
            s.add(Favorite(user_id=user.id, target_type=body.type, target_key=body.key))
    elif row:
        s.delete(row)
    s.commit()
    return {"ok": True, "type": body.type, "key": body.key, "added": body.added}
