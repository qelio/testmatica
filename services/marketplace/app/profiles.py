"""Сборка карточек: имена, фото, онлайн-статус — из других сервисов одним запросом на страницу."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.errors import ApiError

from .config import settings
from .deps import content, identity, media
from .models import Person, TutorProfile
from .schemas import Presence, SubjectRef, TutorCard

UNKNOWN = "Репетитор"
_subjects_cache: tuple[float, dict[str, str]] = (0.0, {})


async def subjects() -> dict[str, str]:
    """Справочник предметов content (id → название), кэш на 5 минут."""
    global _subjects_cache
    fetched, data = _subjects_cache
    if time.monotonic() - fetched < 300 and data:
        return data
    data = {s["id"]: s["name"] for s in await content.get("/subjects")}
    _subjects_cache = (time.monotonic(), data)
    return data


def missing_fields(p: TutorProfile) -> list[str]:
    """Что нужно заполнить, чтобы профиль показывался в поиске (решение №10)."""
    missing = []
    if len(p.headline) < 10:
        missing.append("Коротко о себе (от 10 символов)")
    if len(p.about.strip()) < 50:
        missing.append("Подробный рассказ (от 50 символов)")
    if not p.subject_ids:
        missing.append("Предметы")
    if not p.levels:
        missing.append("С кем занимаетесь")
    if not p.formats:
        missing.append("Формат занятий")
    if not p.price:
        missing.append("Ориентировочная цена")
    return missing


async def names(session: AsyncSession, ids) -> dict[UUID, str]:
    ids = set(ids)
    if not ids:
        return {}
    return dict((await session.execute(select(Person.user_id, Person.full_name).where(Person.user_id.in_(ids)))).all())


async def presence(ids: list[UUID]) -> dict[UUID, Presence]:
    try:
        seen = await identity.post("/internal/users/presence", json={"user_ids": [str(i) for i in ids]}) if ids else {}
    except ApiError:
        seen = {}
    now = datetime.now(UTC)
    out = {}
    for uid in ids:
        raw = seen.get(str(uid))
        at = datetime.fromisoformat(raw) if raw else None
        out[uid] = Presence(online=bool(at and now - at < timedelta(minutes=settings.online_window_minutes)), last_seen_at=at)
    return out


async def photo_urls(file_ids: list[UUID]) -> dict[str, str]:
    if not file_ids:
        return {}
    try:
        found = await media.post("/internal/files/urls", json={"file_ids": [str(i) for i in file_ids]})
    except ApiError:
        return {}
    return {fid: f["url"] for fid, f in found.items() if f.get("url")}


async def cards(session: AsyncSession, profiles: list[TutorProfile]) -> list[TutorCard]:
    who = await names(session, [p.user_id for p in profiles])
    online = await presence([p.user_id for p in profiles])
    photos = await photo_urls([p.photo_file_id for p in profiles if p.photo_file_id])
    return [
        TutorCard(
            user_id=p.user_id, full_name=who.get(p.user_id, UNKNOWN), photo_url=photos.get(str(p.photo_file_id)),
            headline=p.headline, subjects=[SubjectRef(**s) for s in p.subjects], levels=p.levels, formats=p.formats,
            price=p.price, experience_years=p.experience_years, rating=p.rating, reviews_count=p.reviews_count,
            education_verified=p.education_verified, presence=online[p.user_id],
        )
        for p in profiles
    ]
