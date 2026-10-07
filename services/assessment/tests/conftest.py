import os

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["RUN_BACKGROUND"] = "false"
os.environ["CODE_SUBMIT_INTERVAL_SECONDS"] = "0"

import json  # noqa: E402
from uuid import UUID, uuid4  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from testmatica_common.testing import TestTokens, make_envelope  # noqa: E402

from app import handlers, runner  # noqa: E402
from app.config import settings  # noqa: E402
from app.deps import auth, billing, classroom, code_runner, content, db, media, plans, schedule  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Topic  # noqa: E402

tokens = TestTokens()
auth.verifier = tokens.verifier(settings.jwt_issuer, settings.jwt_audience)

SUBJECT = str(uuid4())
SECTION = str(uuid4())  # раздел «Уравнения»
TOPIC = str(uuid4())  # тема «Линейные уравнения» в нём


def bearer(user_id: UUID, roles=("teacher",)) -> dict:
    return {"Authorization": f"Bearer {tokens.issue(user_id, list(roles), settings.jwt_issuer, settings.jwt_audience)}"}


def student(user_id: UUID) -> dict:
    return bearer(user_id, ("student",))


BASIC_TEACHERS: set[str] = set()  # педагоги на тарифе «Базовый»
INTERNAL = {"X-Internal-Token": settings.internal_token}


class Fakes:
    """Песочница (решение «правильное», если в коде есть слово 'correct') и media."""

    def __init__(self) -> None:
        self.runner_up = True
        self.files: dict[str, dict] = {}
        self.runs: list[dict] = []
        self.groups: dict[str, dict] = {}  # id группы → {"teacher_id", "member_ids"}
        self.lessons: dict[str, str] = {}  # id занятия → id педагога
        self.modules: dict[str, dict] = {}  # id модуля курса → сведения из content (/internal/modules/lookup)

    def runner(self, request: httpx.Request) -> httpx.Response:
        if not self.runner_up:
            return httpx.Response(503)
        body = json.loads(request.content)
        self.runs.append(body)
        n = len(body["tests"])
        if "correct" in body["code"]:
            cases = [{"number": i + 1, "status": "passed", "time_ms": 5, "output": "ok", "error": ""} for i in range(n)]
            return httpx.Response(200, json={"passed": True, "cases": cases})
        cases = [{"number": 1, "status": "passed", "time_ms": 5, "output": "ok", "error": ""},
                 {"number": 2, "status": "wrong_answer", "time_ms": 7, "output": "41", "error": ""}]
        return httpx.Response(200, json={"passed": False, "cases": cases[: max(1, min(2, n))]})

    def classroom(self, request: httpx.Request) -> httpx.Response:
        group = self.groups.get(request.url.path.rsplit("/", 1)[-1])
        if group is None or group["teacher_id"] != request.url.params["teacher_id"]:
            return httpx.Response(404, json={"error": {"code": "group_not_found", "message": "Группа не найдена"}})
        return httpx.Response(200, json=group)

    def schedule(self, request: httpx.Request) -> httpx.Response:
        lesson_id = request.url.path.rsplit("/", 1)[-1]
        if self.lessons.get(lesson_id) != request.url.params["teacher_id"]:
            return httpx.Response(404, json={"error": {"code": "lesson_not_found", "message": "Занятие не найдено"}})
        return httpx.Response(200, json={"id": lesson_id})

    def content(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        out = []
        for mid in body["module_ids"]:
            m = self.modules.get(mid)
            if m is not None:
                out.append(m | {"id": mid, "usable": m["owner_id"] == body["user_id"] or m.get("published", False)})
        return httpx.Response(200, json=out)

    def module(self, owner: UUID, theme="comics", published=False) -> str:
        mid = str(uuid4())
        self.modules[mid] = {"title": "Уравнения", "section_title": "Алгебра", "course_id": str(uuid4()), "course_title": "Математика 7",
                             "course_theme": theme, "owner_id": str(owner), "published": published}
        return mid

    def file(self, owner: UUID, name="решение.pdf") -> str:
        fid = str(uuid4())
        self.files[fid] = {"id": fid, "owner": str(owner), "filename": name, "mime": "application/pdf", "size": 10}
        return fid

    def media(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        pub = lambda f, url=None: {k: f[k] for k in ("id", "filename", "mime", "size")} | {  # noqa: E731
            "purpose": "answer", "created_at": "2026-09-25T00:00:00Z", "url": url}
        if request.url.path.endswith("/claim"):
            out = []
            for fid in body["file_ids"]:
                f = self.files.get(fid)
                if f is None or f["owner"] != body["owner_id"]:
                    return httpx.Response(422, json={"error": {"code": "invalid_attachment", "message": "Нет"}})
                out.append(pub(f))
            return httpx.Response(200, json=out)
        return httpx.Response(200, json={i: pub(self.files[i], f"http://s3/{i}") for i in body["file_ids"] if i in self.files})


@pytest.fixture(autouse=True)
def fakes() -> Fakes:
    f = Fakes()
    code_runner.transport = httpx.MockTransport(f.runner)
    media.transport = httpx.MockTransport(f.media)
    classroom.transport = httpx.MockTransport(f.classroom)
    schedule.transport = httpx.MockTransport(f.schedule)
    content.transport = httpx.MockTransport(f.content)
    billing.transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={u: "basic" if u in BASIC_TEACHERS else "free" for u in json.loads(r.content)["user_ids"]})
    )
    plans.reset()
    BASIC_TEACHERS.clear()
    return f


@pytest.fixture(scope="session", autouse=True)
async def schema():
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await db.dispose()


@pytest.fixture(autouse=True)
async def clean():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with db.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    async with db.sessionmaker() as s, s.begin():
        s.add(Topic(id=UUID(SECTION), subject_id=UUID(SUBJECT), subject_name="Алгебра", title="Уравнения"))
        await s.flush()
        s.add(Topic(id=UUID(TOPIC), subject_id=UUID(SUBJECT), subject_name="Алгебра", parent_id=UUID(SECTION),
                    title="Линейные уравнения"))


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def apply(handler, type_: str, actor=None, **data) -> None:
    async with db.sessionmaker() as s, s.begin():
        env = make_envelope(type_, {k: (str(v) if isinstance(v, UUID) else v) for k, v in data.items()}, actor_id=actor)
        await handler(env, s)


async def link(teacher: UUID, pupil: UUID) -> None:
    await apply(handlers.on_classroom_event, "classroom.link.created", teacher_id=teacher, student_id=pupil, link_id=uuid4())


async def run_code_checks() -> None:
    """Выполнить команды проверки кода из outbox (в тестах брокера нет)."""
    async with db.engine.connect() as conn:
        rows = (await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = 'assessment.code'"))).scalars().all()
    for payload in rows:
        async with db.sessionmaker() as s, s.begin():
            from testmatica_common.messaging import Envelope

            await runner.on_code_check(Envelope.model_validate(payload), s)


async def outbox(key: str) -> list[dict]:
    async with db.engine.connect() as conn:
        rows = await conn.execute(text("SELECT payload FROM outbox WHERE routing_key = :k ORDER BY created_at"), {"k": key})
        return [r[0] for r in rows]


CHOICE = {
    "title": "Корень уравнения", "statement": "Решите $2x - 6 = 0$", "type": "choice", "topic_id": TOPIC,
    "subject_name": "Алгебра", "difficulty": 1, "tags": ["Уравнения", "7 класс"], "explanation": "Переносим 6 и делим на 2.",
    "options": [{"text": "3", "is_correct": True}, {"text": "-3"}, {"text": "12"}],
}
MULTI = CHOICE | {"title": "Чётные числа", "statement": "Выберите чётные", "options": [
    {"text": "2", "is_correct": True}, {"text": "3"}, {"text": "4", "is_correct": True}]}
SHORT = {
    "title": "Десятичная дробь", "statement": "Запишите 7/2 десятичной дробью", "type": "short", "topic_id": TOPIC,
    "answers": [{"mode": "exact", "value": "3.5"}, {"mode": "regex", "value": r"три\s+с\s+половиной"}],
}
CODE = {
    "title": "Сумма двух чисел", "statement": "Считайте a и b, выведите a+b", "type": "code", "topic_id": TOPIC,
    "starter_code": "a, b = map(int, input().split())\n", "time_limit_s": 1, "memory_limit_mb": 64,
    "tests": [{"input": "2 3", "expected": "5"}, {"input": "40 2", "expected": "42"}],
}
LONG = {
    "title": "Доказательство", "statement": "Докажите, что корень из 2 иррационален", "type": "long", "topic_id": TOPIC,
    "file_mode": "required",
}
