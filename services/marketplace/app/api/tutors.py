"""Профиль репетитора, образование, поиск и публичная страница."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from testmatica_common.auth import ROLE_ADMIN, ROLE_MODERATOR, ROLE_TEACHER, Principal
from testmatica_common.errors import ApiError

from .. import profiles
from ..config import settings
from ..deps import auth, db, media, outbox
from ..models import APPROVED, PENDING, EducationDoc, Person, TutorProfile
from ..schemas import EducationIn, EducationOut, MyProfile, ProfileIn, SearchPage, TutorPublic

router = APIRouter(tags=["tutors"])
teacher = auth.require(ROLE_TEACHER)


async def _profile(session: AsyncSession, user_id: UUID, lock: bool = False) -> TutorProfile:
    """Профиль педагога; создаётся пустым (не в поиске) при первом обращении."""
    p = await session.get(TutorProfile, user_id, with_for_update=lock)
    if p is None:
        p = TutorProfile(user_id=user_id, subjects=[], subject_ids=[], levels=[], formats=[])
        session.add(p)
        await session.flush()
    return p


async def _education(session: AsyncSession, user_id: UUID, only_approved: bool) -> list[EducationDoc]:
    query = select(EducationDoc).where(EducationDoc.user_id == user_id).order_by(EducationDoc.year.desc())
    if only_approved:
        query = query.where(EducationDoc.status == APPROVED)
    return list((await session.execute(query)).scalars())


def _public_doc(d: EducationDoc) -> EducationOut:
    return EducationOut(id=d.id, title=d.title, institution=d.institution, year=d.year)


def _own_doc(d: EducationDoc, url: str | None = None) -> EducationOut:
    return EducationOut(id=d.id, title=d.title, institution=d.institution, year=d.year, status=d.status, comment=d.comment,
                        filename=d.filename, file_url=url)


async def _public(session: AsyncSession, p: TutorProfile, viewer: Principal | None) -> TutorPublic:
    [card] = await profiles.cards(session, [p])
    # ТЗ: публично виден только бейдж; список документов (без файлов) — тем, кто вошёл на платформу.
    docs = [_public_doc(d) for d in await _education(session, p.user_id, only_approved=True)] if viewer else []
    insider = viewer is not None and (viewer.user_id == p.user_id or viewer.has_any(ROLE_MODERATOR))
    return TutorPublic(**card.model_dump(), about=p.about, published=p.published,
                       share_url=f"{settings.web_base_url}/tutors/{p.user_id}", education=docs,
                       blocked_reason=p.blocked_reason if insider else None)


async def _my(session: AsyncSession, p: TutorProfile, principal: Principal) -> MyProfile:
    docs = await _education(session, p.user_id, only_approved=False)
    return MyProfile(
        blocked_reason=p.blocked_reason,
        profile=await _public(session, p, principal), photo_file_id=p.photo_file_id, missing=profiles.missing_fields(p),
        education=[_own_doc(d) for d in docs],
    )


@router.get("/me/profile", response_model=MyProfile)
async def my_profile(principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> MyProfile:
    p = await _profile(session, principal.user_id)
    await session.commit()
    return await _my(session, p, principal)


@router.put("/me/profile", response_model=MyProfile)
async def update_profile(body: ProfileIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> MyProfile:
    """Профиль и переключатель «Показывать меня в поиске репетиторов». Включить можно только заполненный профиль."""
    p = await _profile(session, principal.user_id, lock=True)
    known = await profiles.subjects()
    unknown = [s for s in body.subject_ids if str(s) not in known]
    if unknown:
        raise ApiError(422, "unknown_subject", "Такого предмета нет в справочнике")
    if body.photo_file_id and body.photo_file_id != p.photo_file_id:
        await media.post("/internal/files/claim", json={
            "owner_id": str(principal.user_id), "purpose": "avatar", "file_ids": [str(body.photo_file_id)], "claimed_by": "marketplace",
        })
    p.headline, p.about, p.photo_file_id = body.headline, body.about.strip(), body.photo_file_id
    ids = list(dict.fromkeys(body.subject_ids))
    p.subject_ids, p.subjects = ids, [{"id": str(i), "name": known[str(i)]} for i in ids]
    p.levels, p.formats = list(dict.fromkeys(body.levels)), list(dict.fromkeys(body.formats))
    p.price, p.experience_years = body.price, body.experience_years
    if body.published and p.blocked_reason:
        raise ApiError(403, "profile_blocked", f"Профиль скрыт администратором: {p.blocked_reason}")
    if body.published and (missing := profiles.missing_fields(p)):
        raise ApiError(422, "profile_incomplete", "Чтобы появиться в поиске, заполните: " + ", ".join(missing).lower(),
                       {"missing": missing})
    was = p.published
    p.published = body.published
    p.updated_at = datetime.now(UTC)
    if was != p.published:
        await outbox.event(session, "marketplace.profile.published" if p.published else "marketplace.profile.hidden",
                           {"user_id": str(p.user_id)}, actor_id=principal.user_id)
    await session.commit()
    return await _my(session, p, principal)


@router.post("/me/education", response_model=MyProfile, status_code=201)
async def add_education(body: EducationIn, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> MyProfile:
    """Документ об образовании — на проверку модератору (FIFO-очередь)."""
    claimed = await media.post("/internal/files/claim", json={
        "owner_id": str(principal.user_id), "purpose": "document", "file_ids": [str(body.file_id)], "claimed_by": "marketplace",
    })
    doc = EducationDoc(user_id=principal.user_id, title=body.title, institution=body.institution, year=body.year,
                       file_id=body.file_id, filename=claimed[0]["filename"], status=PENDING)
    session.add(doc)
    await session.flush()
    name = (await profiles.names(session, [principal.user_id])).get(principal.user_id, profiles.UNKNOWN)
    await outbox.event(session, "marketplace.education.submitted", {
        "doc_id": str(doc.id), "user_id": str(principal.user_id), "title": f"{doc.title} — {name}",
        "institution": doc.institution, "year": doc.year,
    }, actor_id=principal.user_id)
    p = await _profile(session, principal.user_id)
    await session.commit()
    return await _my(session, p, principal)


@router.delete("/me/education/{doc_id}", response_model=MyProfile)
async def delete_education(doc_id: UUID, principal: Principal = Depends(teacher), session: AsyncSession = Depends(db.session)) -> MyProfile:
    doc = await session.get(EducationDoc, doc_id, with_for_update=True)
    if doc is None or doc.user_id != principal.user_id:
        raise ApiError(404, "doc_not_found", "Документ не найден")
    if doc.status == PENDING:
        await outbox.event(session, "marketplace.education.withdrawn", {"doc_id": str(doc.id), "user_id": str(doc.user_id)},
                           actor_id=principal.user_id)
    await session.delete(doc)
    p = await _profile(session, principal.user_id, lock=True)
    await session.flush()
    await refresh_badge(session, p)
    await session.commit()
    return await _my(session, p, principal)


async def refresh_badge(session: AsyncSession, p: TutorProfile) -> None:
    """Бейдж «Образование подтверждено» — если одобрен хотя бы один документ."""
    approved = await session.scalar(
        select(func.count()).select_from(EducationDoc).where(EducationDoc.user_id == p.user_id, EducationDoc.status == APPROVED)
    )
    p.education_verified = bool(approved)


@router.get("/tutors", response_model=SearchPage)
async def search(
    subject_id: UUID | None = None,
    level: str | None = Query(None, pattern="^(1-4|5-9|10-11|student|adult)$"),
    format: str | None = Query(None, pattern="^(individual|group)$"),
    price_min: int | None = Query(None, ge=0),
    price_max: int | None = Query(None, ge=0),
    min_rating: float | None = Query(None, ge=1, le=10),
    verified: bool = Query(False, description="Только с подтверждённым образованием"),
    q: str | None = Query(None, max_length=100),
    sort: str = Query("rating", pattern="^(rating|price_asc|price_desc|new)$"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(db.session),
) -> SearchPage:
    """Поиск репетиторов — открыт и без входа (ТЗ, раздел 4)."""
    query = select(TutorProfile).where(TutorProfile.published.is_(True))
    if subject_id:
        query = query.where(TutorProfile.subject_ids.contains([subject_id]))
    if level:
        query = query.where(TutorProfile.levels.contains([level]))
    if format:
        query = query.where(TutorProfile.formats.contains([format]))
    if price_min is not None:
        query = query.where(TutorProfile.price >= price_min)
    if price_max is not None:
        query = query.where(TutorProfile.price <= price_max)
    if min_rating is not None:
        query = query.where(TutorProfile.rating >= min_rating)
    if verified:
        query = query.where(TutorProfile.education_verified.is_(True))
    if q:
        like = f"%{q.strip()}%"
        query = query.join(Person, Person.user_id == TutorProfile.user_id, isouter=True).where(
            or_(Person.full_name.ilike(like), TutorProfile.headline.ilike(like), TutorProfile.about.ilike(like))
        )
    order = {
        "rating": [nulls_last(TutorProfile.rating.desc()), TutorProfile.reviews_count.desc(), TutorProfile.updated_at.desc()],
        "price_asc": [TutorProfile.price.asc()],
        "price_desc": [TutorProfile.price.desc()],
        "new": [TutorProfile.created_at.desc()],
    }[sort]
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(*order).limit(limit).offset(offset))).scalars().all()
    return SearchPage(items=await profiles.cards(session, list(rows)), total=total or 0)


@router.get("/tutors/{user_id}", response_model=TutorPublic)
async def tutor(
    user_id: UUID, principal: Principal | None = Depends(auth.optional), session: AsyncSession = Depends(db.session)
) -> TutorPublic:
    """Публичная страница по ссылке «Поделиться» — без регистрации. Скрытый профиль видит только владелец."""
    p = await session.get(TutorProfile, user_id)
    owner_or_staff = principal is not None and (principal.user_id == user_id or principal.has_any(ROLE_MODERATOR))
    if p is None or not (p.published or owner_or_staff):
        raise ApiError(404, "tutor_not_found", "Профиль не найден")
    return await _public(session, p, principal)


@router.get("/moderation/education/{doc_id}", response_model=EducationOut)
async def education_for_moderator(
    doc_id: UUID, _: Principal = Depends(auth.require(ROLE_MODERATOR)), session: AsyncSession = Depends(db.session)
) -> EducationOut:
    """Документ с файлом — модератору для проверки."""
    doc = await session.get(EducationDoc, doc_id)
    if doc is None:
        raise ApiError(404, "doc_not_found", "Документ не найден")
    found = await media.post("/internal/files/urls", json={"file_ids": [str(doc.file_id)]})
    return _own_doc(doc, (found.get(str(doc.file_id)) or {}).get("url"))


# ---------- администратор ----------


class HideIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/admin/tutors/{user_id}/hide", response_model=TutorPublic)
async def admin_hide(
    user_id: UUID, body: HideIn, principal: Principal = Depends(auth.require(ROLE_ADMIN)), session: AsyncSession = Depends(db.session)
) -> TutorPublic:
    """Скрыть профиль репетитора из поиска и по ссылке; включить показ обратно педагог не сможет, пока администратор не вернёт."""
    p = await _profile(session, user_id, lock=True)
    p.published, p.blocked_reason = False, body.reason.strip()
    await outbox.event(session, "marketplace.profile.blocked", {"user_id": str(user_id), "reason": p.blocked_reason},
                       actor_id=principal.user_id)
    await session.commit()
    return await _public(session, p, principal)


@router.post("/admin/tutors/{user_id}/unhide", response_model=TutorPublic)
async def admin_unhide(
    user_id: UUID, principal: Principal = Depends(auth.require(ROLE_ADMIN)), session: AsyncSession = Depends(db.session)
) -> TutorPublic:
    """Снять запрет. Показ в поиске педагог включит сам."""
    p = await _profile(session, user_id, lock=True)
    if p.blocked_reason:
        p.blocked_reason = None
        await outbox.event(session, "marketplace.profile.unblocked", {"user_id": str(user_id)}, actor_id=principal.user_id)
        await session.commit()
    return await _public(session, p, principal)
