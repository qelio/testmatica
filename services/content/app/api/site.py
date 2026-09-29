"""Главная страница и новости: публичная выдача и редактирование администратором."""

import re
import secrets
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, Principal
from testmatica_common.errors import ApiError

from ..deps import auth, db, media, outbox
from ..models import NEWS_DRAFT, NEWS_PUBLISHED, News, SiteSetting
from ..site import DEFAULT_LANDING, Landing

router = APIRouter(tags=["site"])
admin = auth.require(ROLE_ADMIN)

_TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", [
    "a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "ts",
    "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"], strict=True))


class NewsSummary(BaseModel):
    id: UUID
    slug: str
    title: str
    summary: str
    cover_url: str | None
    status: str
    published_at: datetime | None
    updated_at: datetime


class LandingOut(Landing):
    hero_image_url: str | None = None
    latest_news: list[NewsSummary] = Field(default_factory=list)
    updated_at: datetime | None = None


class NewsOut(NewsSummary):
    body: str
    cover_file_id: UUID | None


class NewsPage(BaseModel):
    items: list[NewsSummary]
    total: int


class NewsIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=120, description="Адрес /news/<slug>; пусто — из заголовка")
    summary: str = Field("", max_length=500)
    body: str = Field("", max_length=50_000)
    cover_file_id: UUID | None = None
    status: str = Field(NEWS_DRAFT, pattern="^(draft|published)$")

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", v.strip()):
            raise ValueError("Адрес — латинские буквы, цифры и дефисы")
        return v.strip()


def slugify(title: str) -> str:
    text = "".join(_TRANSLIT.get(ch, ch) for ch in title.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:80] or "news"


async def _urls(ids) -> dict[str, str]:
    ids = [str(i) for i in ids if i]
    if not ids:
        return {}
    found = await media.post("/internal/files/urls", json={"file_ids": ids})
    return {k: v["url"] for k, v in found.items() if v.get("url")}


async def _claim(principal: Principal, file_ids: list[UUID]) -> None:
    """Новые картинки — закрепить за сайтом (иначе media удалит их как брошенные)."""
    if file_ids:
        await media.post("/internal/files/claim", json={
            "owner_id": str(principal.user_id), "purpose": "site", "file_ids": [str(f) for f in file_ids], "claimed_by": "content"})


async def _landing(session: AsyncSession) -> tuple[Landing, datetime | None]:
    row = await session.get(SiteSetting, "landing")
    if row is None:
        return DEFAULT_LANDING, None
    return Landing.model_validate(row.value), row.updated_at


def _summary(n: News, urls: dict[str, str]) -> NewsSummary:
    return NewsSummary(id=n.id, slug=n.slug, title=n.title, summary=n.summary, cover_url=urls.get(str(n.cover_file_id)),
                       status=n.status, published_at=n.published_at, updated_at=n.updated_at)


def _full(n: News, urls: dict[str, str]) -> NewsOut:
    return NewsOut(**_summary(n, urls).model_dump(), body=n.body, cover_file_id=n.cover_file_id)


async def _published(session: AsyncSession, limit: int, offset: int = 0) -> tuple[list[News], int]:
    q = select(News).where(News.status == NEWS_PUBLISHED)
    total = await session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await session.execute(q.order_by(News.published_at.desc()).limit(limit).offset(offset))).scalars().all()
    return list(rows), total


# ---------- публично ----------


@router.get("/site/landing", response_model=LandingOut)
async def landing(session: AsyncSession = Depends(db.session)) -> LandingOut:
    """Всё для главной одним запросом: разделы, картинка, последние новости. Преподавателей веб берёт из marketplace."""
    data, updated = await _landing(session)
    news, _ = await _published(session, data.news.count) if data.sections.news else ([], 0)
    urls = await _urls([data.hero.image_file_id, *(n.cover_file_id for n in news)])
    return LandingOut(**data.model_dump(), hero_image_url=urls.get(str(data.hero.image_file_id)),
                      latest_news=[_summary(n, urls) for n in news], updated_at=updated)


@router.get("/site/news", response_model=NewsPage)
async def news_list(limit: int = Query(12, ge=1, le=50), offset: int = Query(0, ge=0), session: AsyncSession = Depends(db.session)) -> NewsPage:
    rows, total = await _published(session, limit, offset)
    urls = await _urls(n.cover_file_id for n in rows)
    return NewsPage(items=[_summary(n, urls) for n in rows], total=total)


@router.get("/site/news/{slug}", response_model=NewsOut)
async def news_item(slug: str, principal: Principal | None = Depends(auth.optional), session: AsyncSession = Depends(db.session)) -> NewsOut:
    """Опубликованная — всем; черновик — только администратору (предпросмотр)."""
    n = await session.scalar(select(News).where(News.slug == slug))
    if n is None or (n.status != NEWS_PUBLISHED and not (principal and principal.has_any(ROLE_ADMIN))):
        raise ApiError(404, "news_not_found", "Новость не найдена")
    return _full(n, await _urls([n.cover_file_id]))


# ---------- администратор ----------


@router.get("/admin/site/landing", response_model=LandingOut)
async def admin_landing(_: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> LandingOut:
    data, updated = await _landing(session)
    urls = await _urls([data.hero.image_file_id])
    return LandingOut(**data.model_dump(), hero_image_url=urls.get(str(data.hero.image_file_id)), updated_at=updated)


@router.put("/admin/site/landing", response_model=LandingOut)
async def save_landing(body: Landing, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> LandingOut:
    row = await session.get(SiteSetting, "landing", with_for_update=True)
    old = Landing.model_validate(row.value) if row else DEFAULT_LANDING
    if body.hero.image_file_id and body.hero.image_file_id != old.hero.image_file_id:
        await _claim(principal, [body.hero.image_file_id])
    value = body.model_dump(mode="json")
    if row is None:
        session.add(SiteSetting(key="landing", value=value, updated_by=principal.user_id))
    else:
        row.value, row.updated_by = value, principal.user_id
    await outbox.event(session, "content.site.updated", {"section": "landing"}, actor_id=principal.user_id)
    await session.commit()
    return await admin_landing(principal, session)


@router.get("/admin/site/news", response_model=list[NewsSummary])
async def admin_news(_: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> list[NewsSummary]:
    rows = (await session.execute(select(News).order_by(News.created_at.desc()).limit(200))).scalars().all()
    urls = await _urls(n.cover_file_id for n in rows)
    return [_summary(n, urls) for n in rows]


@router.get("/admin/site/news/{news_id}", response_model=NewsOut)
async def admin_news_item(news_id: UUID, _: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> NewsOut:
    n = await session.get(News, news_id)
    if n is None:
        raise ApiError(404, "news_not_found", "Новость не найдена")
    return _full(n, await _urls([n.cover_file_id]))


async def _unique_slug(session: AsyncSession, slug: str, own_id: UUID | None) -> str:
    candidate = slug
    while True:
        other = await session.scalar(select(News.id).where(News.slug == candidate))
        if other is None or other == own_id:
            return candidate
        candidate = f"{slug}-{secrets.token_hex(2)}"


async def _apply(session: AsyncSession, n: News, body: NewsIn, principal: Principal, explicit_slug: bool) -> None:
    if body.cover_file_id and body.cover_file_id != n.cover_file_id:
        await _claim(principal, [body.cover_file_id])
    wanted = body.slug or (n.slug if n.slug else slugify(body.title))
    if body.slug and explicit_slug:
        taken = await session.scalar(select(News.id).where(News.slug == body.slug))
        if taken is not None and taken != n.id:
            raise ApiError(409, "slug_taken", "Такой адрес уже занят другой новостью")
    n.slug = await _unique_slug(session, wanted, n.id)
    n.title, n.summary, n.body, n.cover_file_id = body.title.strip(), body.summary.strip(), body.body, body.cover_file_id
    if body.status == NEWS_PUBLISHED and n.status != NEWS_PUBLISHED:
        n.published_at = n.published_at or datetime.now(UTC)
    n.status = body.status


@router.post("/admin/site/news", response_model=NewsOut, status_code=201)
async def create_news(body: NewsIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> NewsOut:
    n = News(author_id=principal.user_id, slug="", status=NEWS_DRAFT)
    await _apply(session, n, body, principal, explicit_slug=True)
    session.add(n)
    await session.flush()
    await outbox.event(session, "content.news.saved", {"news_id": str(n.id), "title": n.title, "status": n.status}, actor_id=principal.user_id)
    await session.commit()
    await session.refresh(n)  # updated_at выставляет база
    return _full(n, await _urls([n.cover_file_id]))


@router.put("/admin/site/news/{news_id}", response_model=NewsOut)
async def update_news(news_id: UUID, body: NewsIn, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> NewsOut:
    n = await session.get(News, news_id, with_for_update=True)
    if n is None:
        raise ApiError(404, "news_not_found", "Новость не найдена")
    await _apply(session, n, body, principal, explicit_slug=True)
    await outbox.event(session, "content.news.saved", {"news_id": str(n.id), "title": n.title, "status": n.status}, actor_id=principal.user_id)
    await session.commit()
    await session.refresh(n)  # updated_at выставляет база
    return _full(n, await _urls([n.cover_file_id]))


@router.delete("/admin/site/news/{news_id}", status_code=204)
async def delete_news(news_id: UUID, principal: Principal = Depends(admin), session: AsyncSession = Depends(db.session)) -> None:
    n = await session.get(News, news_id, with_for_update=True)
    if n is None:
        raise ApiError(404, "news_not_found", "Новость не найдена")
    await outbox.event(session, "content.news.deleted", {"news_id": str(n.id), "title": n.title}, actor_id=principal.user_id)
    await session.delete(n)
    await session.commit()
