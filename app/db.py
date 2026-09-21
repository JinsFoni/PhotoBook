"""SQLAlchemy 模型 — 全部 12 张表。库中只存元数据,文件在磁盘 volume。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---- 用户与权限 -----------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user")  # user | admin
    avatar_seed: Mapped[str] = mapped_column(String(64), default="")
    language: Mapped[str] = mapped_column(String(8), default="")  # 界面语言(""=跟随站点默认)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete")


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


# ---- 内容库 ---------------------------------------------------------------

class Model(Base):
    __tablename__ = "models"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    stage_name: Mapped[str | None] = mapped_column(String(120), default=None)
    avatar_path: Mapped[str | None] = mapped_column(String(400), default=None)  # /media 相对路径
    hero_path: Mapped[str | None] = mapped_column(String(400), default=None)
    gender: Mapped[str | None] = mapped_column(String(20), default=None)
    age: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[str | None] = mapped_column(String(30), default=None)
    measurements: Mapped[str | None] = mapped_column(String(60), default=None)
    agency: Mapped[str | None] = mapped_column(String(120), default=None)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    since: Mapped[str | None] = mapped_column(String(20), default=None)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft|published|hidden
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collections: Mapped[list["Collection"]] = relationship(back_populates="model")
    tags: Mapped[list["Tag"]] = relationship(secondary="model_tags", lazy="selectin")


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    cover_photo_id: Mapped[int | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"), default=None)
    published_at: Mapped[str | None] = mapped_column(String(20), default=None)  # YYYY.MM.DD
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft|published|hidden
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_weight: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    model: Mapped[Model | None] = relationship(back_populates="collections")
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan",
        order_by="Photo.sort_order", lazy="selectin",
        foreign_keys="Photo.collection_id")
    tags: Mapped[list["Tag"]] = relationship(secondary="collection_tags", lazy="selectin")

    __table_args__ = (Index("ix_collections_status_date", "status", "published_at"),)


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))       # /media 相对路径
    width: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[int | None] = mapped_column(default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    collection: Mapped[Collection] = relationship(back_populates="photos",
                                                   foreign_keys=[collection_id])

    __table_args__ = (UniqueConstraint("collection_id", "filename", name="uq_photo_file"),)


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)

    models: Mapped[list[Model]] = relationship(secondary="model_tags", back_populates="tags")
    collections: Mapped[list[Collection]] = relationship(secondary="collection_tags", back_populates="tags")


class ModelTag(Base):
    __tablename__ = "model_tags"
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class CollectionTag(Base):
    __tablename__ = "collection_tags"
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


# ---- 用户行为 ---------------------------------------------------------------

class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(12))  # model | collection | photo
    target_key: Mapped[str] = mapped_column(String(255))  # slug 或 collection:idx
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_key", name="uq_fav"),)


# ---- 采集子系统(需求 §29)----------------------------------------------------

class HarvestJob(Base):
    __tablename__ = "harvest_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    serial: Mapped[int] = mapped_column(Integer, index=True)       # 源站序号
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    model_name: Mapped[str | None] = mapped_column(String(120), default=None)
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    # queued | parsing | downloading | extracting | done | exists | skipped | failed
    bytes_done: Mapped[int] = mapped_column(Integer, default=0)
    bytes_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(10), default="auto")  # auto | manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (Index("ix_jobs_status_id", "status", "id"),)


class HarvestHistory(Base):
    __tablename__ = "harvest_history"
    serial: Mapped[int] = mapped_column(Integer, primary_key=True)  # 源站序号,去重判据
    status: Mapped[str] = mapped_column(String(12))
    title: Mapped[str | None] = mapped_column(String(255), default=None)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---- 配置 -------------------------------------------------------------------

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)
