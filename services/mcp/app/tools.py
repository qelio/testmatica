"""Функции платформы для Claude (решение №41): задачи в банк и теория в библиотеку.

Описания функций и полей — для Claude: по ним он решает, что и как вызвать. Всё создаётся от имени владельца
ключа как его личные материалы (задача — «личная», курс — черновик); в публичный банк и библиотеку — через
обычную модерацию в интерфейсе."""

from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from .platform import api_key, call, link, localize_images, session_for, upload_image as store_image

INSTRUCTIONS = """Ты работаешь с образовательной платформой ТестМатика от имени педагога.
Тексты — Markdown; формулы — LaTeX: $…$ в строке и $$…$$ отдельной строкой. Картинки — ![подпись](https://…)
или вшитые ![подпись](data:image/png;base64,…): и те и другие переносятся в хранилище платформы. Картинку из файла
загрузи upload_image (base64) и вставь полученный Markdown в текст материала, условие, варианты или разбор задачи.
Перед созданием задачи найди тему рубрикатора (list_topics) и при необходимости задания ЕГЭ/ОГЭ (list_exam_items),
проверь, нет ли похожей задачи (search_tasks). У каждой задачи короткий номер — «(100345)»; по нему её можно найти
и исправить. Теория: курс → раздел → модуль → материалы (текст, карточка теории, задача из банка).
Тесты собираются из задач банка; тест можно привязать к модулю курса (свой курс или опубликованный —
search_library_courses): тогда он оформлен как курс. У автора курса тест — часть курса: shared=true — публичный (ученики
проходят его сами), shared=false — «для педагогов» (проверочная, контрольная: видят и назначают все педагоги); другим
он виден после того, как модератор примет его вместе с курсом. Тест к чужому курсу — личный, виден только его автору.
Всё создаётся как личные материалы педагога; в публичный банк — через модерацию в интерфейсе.
После работы перечисли созданное со ссылками."""

mcp = MCPServer(name="ТестМатика", instructions=INSTRUCTIONS, website_url="https://testmatica.ru")

TaskType = Literal["choice", "short", "long", "code"]
# Оформление курса (решение №42): classic — как вся платформа; comics — игровое: толстые контуры, яркие цвета,
# крупный округлый шрифт; подходит для 5–9 классов и курсов-«миссий».
Theme = Annotated[Literal["classic", "comics"], Field(description="Оформление для учеников: classic — строгое, "
                                                                     "comics — игровое «Комикс» для 5–9 классов")]


def _key(ctx: Context) -> str:
    return api_key(ctx.headers)


# ---------- картинки ----------


@mcp.tool()
async def upload_image(
    ctx: Context,
    image: Annotated[str, Field(description="Картинка в base64 или data:image/png;base64,… — PNG, JPEG, GIF или WebP, до 20 МБ")],
    name: Annotated[str, Field(description="Короткое название (подпись)")] = "картинка",
) -> dict:
    """Загрузить картинку на платформу. Возвращает Markdown — вставь его в текст материала (add_material, update_material),
    в условие, варианты или разбор задачи (create_task, update_task) или в описание теста. Картинки по ссылкам https://…
    и вшитые data:image/… в тексте загружаются сами — эта функция нужна для картинок из файлов."""
    path = await store_image(_key(ctx), image, name)
    return {"markdown": f"![{name}]({path})", "url": link(path)}


# ---------- справочники ----------


@mcp.tool()
async def whoami(ctx: Context) -> dict:
    """Кто подключён: имя педагога, от чьего имени создаются материалы."""
    _, name = await session_for(_key(ctx))
    return {"full_name": name}


@mcp.tool()
async def list_subjects(ctx: Context) -> list[dict]:
    """Предметы платформы (id и название) — для курса библиотеки и для выбора темы."""
    rows = await call(_key(ctx), "content", "GET", "/subjects")
    return [{"id": s["id"], "name": s["name"]} for s in rows]


@mcp.tool()
async def list_topics(
    ctx: Context,
    subject: Annotated[str | None, Field(description="Название предмета (например, «Алгебра») — чтобы сузить список")] = None,
) -> list[dict]:
    """Рубрикатор банка задач: разделы и темы с id. Задачу кладут в тему (topic_id), раздел — родитель темы."""
    rows = await call(_key(ctx), "assessment", "GET", "/topics", params={"scope": "public"})
    if subject:
        rows = [t for t in rows if t["subject_name"].lower() == subject.strip().lower()]
    sections = {t["id"]: t for t in rows if not t["parent_id"]}
    return [
        {"id": t["id"], "subject": t["subject_name"],
         "section": sections[t["parent_id"]]["title"] if t["parent_id"] in sections else None,
         "title": t["title"], "is_section": not t["parent_id"]}
        for t in rows
    ]


@mcp.tool()
async def list_exam_items(
    ctx: Context,
    subject: Annotated[str | None, Field(description="Название предмета — чтобы сузить список")] = None,
) -> list[dict]:
    """Задания ЕГЭ и ОГЭ (номер и название) — к ним можно привязать задачу (exam_item_ids)."""
    exams = await call(_key(ctx), "assessment", "GET", "/exams")
    if subject:
        exams = [e for e in exams if e["subject_name"].lower() == subject.strip().lower()]
    return [
        {"exam": e["title"], "items": [{"id": i["id"], "number": i["number"], "title": i["title"]} for i in e["items"]]}
        for e in exams
    ]


# ---------- задачи ----------


class Option(BaseModel):
    text: str = Field(description="Текст варианта (Markdown, формулы $…$)")
    is_correct: bool = False


class ShortAnswer(BaseModel):
    value: str = Field(description="Правильный ответ")
    mode: Literal["exact", "regex"] = Field("exact", description="exact — точное совпадение (регистр, пробелы, «,»/«.» не важны); regex — шаблон")


class CodeTest(BaseModel):
    input: str = Field("", description="Входные данные (stdin)")
    expected: str = Field(description="Ожидаемый вывод")


class TaskFields(BaseModel):
    title: str = Field(description="Короткое название задачи, например «Задание 6. Процесс, который занимает больше всего памяти»")
    statement: str = Field(description="Условие (Markdown, формулы $…$, картинки ![](https://…))")
    type: TaskType = Field(description="choice — выбор ответа; short — короткий ответ (число, слово); long — развёрнутый, проверяет педагог; code — программа на Python с тестами")
    topic_id: UUID | None = Field(None, description="Тема рубрикатора из list_topics")
    difficulty: int = Field(1, ge=1, le=3, description="1 — базовая, 2 — средняя, 3 — сложная")
    explanation: str = Field("", description="Разбор решения (Markdown) — ученик видит после ответа")
    exam_item_ids: list[UUID] = Field(default_factory=list, description="Задания ЕГЭ/ОГЭ из list_exam_items")
    tags: list[str] = Field(default_factory=list, description="Метки, например «7 класс»")
    options: list[Option] = Field(default_factory=list, description="Для choice: варианты, хотя бы один правильный")
    answers: list[ShortAnswer] = Field(default_factory=list, description="Для short: правильные ответы")
    file_mode: Literal["none", "optional", "required"] = Field("none", description="Для long: можно или нужно прикрепить файл")
    starter_code: str = Field("", description="Для code: заготовка программы")
    tests: list[CodeTest] = Field(default_factory=list, description="Для code: тест-кейсы")
    time_limit_s: float = Field(2, description="Для code: лимит времени, секунд")
    memory_limit_mb: int = Field(128, description="Для code: лимит памяти, МБ")


def _brief(t: dict) -> dict:
    return {"number": t["number"], "id": t["id"], "title": t["title"], "type": t["type"], "difficulty": t["difficulty"],
            "topic": " › ".join(t.get("topic_path") or []) or None, "status": t["status"], "url": link(f"/dashboard/tasks/{t['id']}")}


async def _resolve_task(key: str, ref: str) -> dict:
    """Задача по номеру «100345» / «(100345)» или по id."""
    ref = ref.strip()
    number = ref.strip("()#№ ")
    if number.isdigit():
        for scope in ("mine", "public"):
            page = await call(key, "assessment", "GET", "/tasks", params={"scope": scope, "q": number, "limit": 5})
            hit = next((t for t in page["items"] if t["number"] == int(number)), None)
            if hit:
                return await call(key, "assessment", "GET", f"/tasks/{hit['id']}")
        raise ToolError(f"Задача ({number}) не найдена")
    try:
        UUID(ref)
    except ValueError:
        raise ToolError("Укажите номер задачи, например 100345, или её id") from None
    return await call(key, "assessment", "GET", f"/tasks/{ref}")


async def _payload(key: str, fields: dict[str, Any]) -> dict:
    """Поля задачи → тело запроса; картинки из интернета переносятся к нам."""
    for name in ("statement", "explanation"):
        fields[name] = await localize_images(key, fields.get(name) or "")
    for o in fields.get("options") or []:
        o["text"] = await localize_images(key, o["text"])
    return fields


@mcp.tool()
async def search_tasks(
    ctx: Context,
    query: Annotated[str, Field(description="Текст из названия или условия, либо номер задачи")] = "",
    scope: Annotated[Literal["mine", "public"], Field(description="mine — мои задачи в любом статусе; public — опубликованный банк")] = "mine",
    topic_id: Annotated[UUID | None, Field(description="Тема или раздел из list_topics")] = None,
    type: Annotated[TaskType | None, Field(description="Тип задачи")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 20,
) -> dict:
    """Найти задачи в банке — например, чтобы не создавать повторы или собрать список для теста."""
    params: dict[str, Any] = {"scope": scope, "limit": limit}
    if query.strip():
        params["q"] = query.strip()
    if topic_id:
        params["topic_id"] = str(topic_id)
    if type:
        params["type"] = type
    page = await call(_key(ctx), "assessment", "GET", "/tasks", params=params)
    return {"total": page["total"], "items": [_brief(t) for t in page["items"]]}


@mcp.tool()
async def get_task(ctx: Context, task: Annotated[str, Field(description="Номер задачи (100345) или id")]) -> dict:
    """Задача целиком: условие, варианты и ответы (для своих задач), разбор."""
    t = await _resolve_task(_key(ctx), task)
    return _brief(t) | {k: t.get(k) for k in ("statement", "explanation", "options", "answers", "file_mode", "starter_code", "tests", "tags", "exam_items")}


@mcp.tool()
async def create_task(ctx: Context, task: TaskFields) -> dict:
    """Создать задачу в банке педагога (личная; в публичный банк — через модерацию в интерфейсе). Возвращает номер и ссылку."""
    key = _key(ctx)
    body = await _payload(key, task.model_dump(mode="json"))
    created = await call(key, "assessment", "POST", "/tasks", json=body)
    return _brief(created)


@mcp.tool()
async def update_task(
    ctx: Context,
    task: Annotated[str, Field(description="Номер задачи (100345) или id")],
    changes: Annotated[dict[str, Any], Field(description="Что поменять — поля как у create_task, например {\"answers\": [{\"value\": \"3.5\"}]}")],
) -> dict:
    """Исправить свою задачу: передайте только изменённые поля. Опубликованная задача после правки снова уйдёт на модерацию."""
    key = _key(ctx)
    current = await _resolve_task(key, task)
    if not current.get("can_edit"):
        raise ToolError("Эту задачу нельзя изменить — она не ваша или снята с платформы")
    unknown = set(changes) - set(TaskFields.model_fields)
    if unknown:
        raise ToolError(f"Неизвестные поля: {', '.join(sorted(unknown))}")
    base = {f: current.get(f) for f in TaskFields.model_fields if current.get(f) is not None}
    base["options"] = [{"text": o["text"], "is_correct": bool(o["is_correct"])} for o in current.get("options") or []]
    base["answers"] = current.get("answers") or []
    base["tests"] = current.get("tests") or []
    base["exam_item_ids"] = current.get("exam_item_ids") or [e["id"] for e in current.get("exam_items") or [] if "id" in e]
    merged = TaskFields.model_validate(base | changes)
    body = await _payload(key, merged.model_dump(mode="json"))
    updated = await call(key, "assessment", "PUT", f"/tasks/{current['id']}", json=body)
    return _brief(updated)


# ---------- теория (библиотека) ----------


def _course_out(c: dict) -> dict:
    return {
        "id": c["id"], "title": c["title"], "status": c["status"], "theme": c.get("theme"), "url": link(f"/dashboard/library/course/{c['id']}"),
        "sections": [
            {"id": s["id"], "title": s["title"],
             "modules": [{"id": m["id"], "title": m["title"], "url": link(f"/dashboard/library/module/{m['id']}"),
                          "materials": [{"id": x["id"], "kind": x["kind"], "title": x["title"]} for x in m["materials"]]}
                         for m in s["modules"]]}
            for s in c.get("sections", [])
        ],
    }


@mcp.tool()
async def list_my_courses(ctx: Context) -> list[dict]:
    """Мои курсы в библиотеке (черновики и опубликованные)."""
    rows = await call(_key(ctx), "content", "GET", "/my/courses")
    return [{"id": c["id"], "title": c["title"], "status": c["status"], "subject": (c.get("subject") or {}).get("name"),
             "url": link(f"/dashboard/library/course/{c['id']}")} for c in rows]


@mcp.tool()
async def get_course(ctx: Context, course_id: UUID) -> dict:
    """Структура курса: разделы → модули → материалы (с id — чтобы добавлять и править)."""
    return _course_out(await call(_key(ctx), "content", "GET", f"/courses/{course_id}"))


@mcp.tool()
async def create_course(
    ctx: Context,
    title: str,
    subject_id: Annotated[UUID | None, Field(description="Предмет из list_subjects")] = None,
    description: str = "",
    theme: Theme = "classic",
) -> dict:
    """Создать курс в библиотеке (черновик педагога). Дальше — add_section, add_module, add_material."""
    return _course_out(await call(_key(ctx), "content", "POST", "/courses",
                                  json={"title": title, "subject_id": str(subject_id) if subject_id else None,
                                        "description": description, "theme": theme}))


@mcp.tool()
async def set_course_theme(ctx: Context, course_id: UUID, theme: Theme) -> dict:
    """Сменить оформление курса: страницы курса и модулей у учеников."""
    return _course_out(await call(_key(ctx), "content", "PATCH", f"/nodes/{course_id}", json={"theme": theme}))


async def _add_child(key: str, parent_id: UUID, title: str, description: str, kind: str) -> dict:
    course = await call(key, "content", "POST", f"/nodes/{parent_id}/children", json={"title": title, "description": description})
    out = _course_out(course)
    # Новый узел — последний среди детей родителя.
    if kind == "section":
        node = out["sections"][-1]
    else:
        section = next(s for s in out["sections"] if s["id"] == str(parent_id))
        node = section["modules"][-1]
    return {"id": node["id"], "title": node["title"], "course_id": out["id"], "course_url": out["url"]}


@mcp.tool()
async def add_section(ctx: Context, course_id: UUID, title: str, description: str = "") -> dict:
    """Добавить раздел в курс."""
    return await _add_child(_key(ctx), course_id, title, description, "section")


@mcp.tool()
async def add_module(ctx: Context, section_id: UUID, title: str, description: str = "") -> dict:
    """Добавить модуль (урок) в раздел — в модуль кладутся материалы."""
    return await _add_child(_key(ctx), section_id, title, description, "module")


@mcp.tool()
async def add_material(
    ctx: Context,
    module_id: UUID,
    kind: Annotated[Literal["text", "card", "task"], Field(description="text — текст урока; card — карточка теории (кратко: правило, формула, пример); task — задача из банка")],
    title: Annotated[str | None, Field(description="Название; для задачи — по умолчанию её название")] = None,
    body: Annotated[str, Field(description="Для text и card: содержание (Markdown, формулы $…$, картинки)")] = "",
    task: Annotated[str | None, Field(description="Для task: номер задачи (100345) или id; в курсы — только с автопроверкой")] = None,
) -> dict:
    """Добавить материал в модуль библиотеки."""
    key = _key(ctx)
    payload: dict[str, Any] = {"kind": kind, "title": title}
    if kind == "task":
        if not task:
            raise ToolError("Для материала-задачи укажите задачу: номер или id")
        payload["task_id"] = (await _resolve_task(key, task))["id"]
    else:
        if not body.strip():
            raise ToolError("Пустой материал — заполните body")
        payload["body"] = await localize_images(key, body)
    m = await call(key, "content", "POST", f"/modules/{module_id}/materials", json=payload)
    return {"id": m["id"], "kind": m["kind"], "title": m["title"], "url": link(f"/dashboard/library/module/{module_id}")}


@mcp.tool()
async def update_material(ctx: Context, material_id: UUID, title: str | None = None, body: str | None = None) -> dict:
    """Исправить текст или название материала."""
    key = _key(ctx)
    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = await localize_images(key, body)
    if not payload:
        raise ToolError("Нечего менять — передайте title или body")
    m = await call(key, "content", "PATCH", f"/materials/{material_id}", json=payload)
    return {"id": m["id"], "kind": m["kind"], "title": m["title"], "url": link(f"/dashboard/library/module/{m['module_id']}")}



# ---------- тесты (решения №43, 44) ----------


class TestItem(BaseModel):
    task: str = Field(description="Номер задачи (100345) или id")
    points: int = Field(1, ge=1, le=100, description="Баллы за задание")
    solution_file: bool = Field(False, description="Ученик прикладывает файл с решением (только short и choice); проверяет педагог")


class TestFields(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    grade_level: int = Field(ge=1, le=11, description="Для какого класса (1–11)")
    description: str = Field("", description="Описание для учеников")
    items: list[TestItem] = Field(default_factory=list, description="Задания в порядке теста")
    module_id: UUID | None = Field(None, description="Модуль курса (get_course), к которому относится тест; оформление — как у курса")
    shared: bool = Field(False, description="Для теста автора курса: true — публичный (ученикам и педагогам), false — для педагогов; "
                                            "тест к чужому курсу — всегда личный (false)")
    order_mode: Literal["fixed", "random"] = Field("fixed", description="fixed — как в списке; random — у каждого свой порядок")
    shuffle_options: bool = Field(False, description="Перемешивать варианты ответа")
    time_mode: Literal["none", "total", "per_task"] = Field("none", description="Таймер: нет, на весь тест, на каждое задание")
    time_limit_min: float | None = Field(None, gt=0, le=360, description="Минут на тест или на задание (если есть таймер)")


def _test_brief(t: dict) -> dict:
    module = t.get("module")
    return {
        "id": t["id"], "title": t["title"], "grade_level": t.get("grade_level"),
        "tasks_count": t.get("tasks_count", len(t.get("items") or [])), "max_score": t.get("max_score"),
        "module": {"id": module["id"], "title": module["title"], "course_title": module.get("course_title")} if module else None,
        "shared": t.get("shared", False), "visibility": t.get("visibility"), "published": t.get("published", False),
        "pending_review": t.get("pending", False), "url": link(f"/dashboard/tests/{t['id']}"),
    }


async def _test_body(key: str, fields: TestFields) -> dict:
    items = []
    for item in fields.items:
        task = await _resolve_task(key, item.task)
        items.append({"task_id": task["id"], "points": item.points, "solution_file": item.solution_file})
    body = fields.model_dump(mode="json", exclude={"items", "time_limit_min"})
    body["description"] = await localize_images(key, body["description"])
    body["items"] = items
    body["time_limit_s"] = round(fields.time_limit_min * 60) if fields.time_mode != "none" and fields.time_limit_min else None
    if fields.time_mode != "none" and body["time_limit_s"] is None:
        raise ToolError("Для таймера укажите time_limit_min")
    return body


@mcp.tool()
async def search_library_courses(ctx: Context, query: str = "", subject_id: UUID | None = None) -> list[dict]:
    """Опубликованные курсы публичной библиотеки — к их модулям можно привязать свой тест (get_course — модули)."""
    params = {k: v for k, v in {"q": query.strip(), "subject_id": str(subject_id) if subject_id else ""}.items() if v}
    rows = await call(_key(ctx), "content", "GET", "/catalog", params=params)
    return [{"id": c["id"], "title": c["title"], "author": c["author_name"], "subject": (c.get("subject") or {}).get("name"),
             "url": link(f"/dashboard/library/course/{c['id']}")} for c in rows]


@mcp.tool()
async def list_my_tests(ctx: Context, module_id: Annotated[UUID | None, Field(description="Только привязанные к модулю")] = None) -> list[dict]:
    """Мои тесты: привязка к модулю курса и вид — публичный, для педагогов или личный."""
    rows = await call(_key(ctx), "assessment", "GET", "/tests", params={"module_id": str(module_id)} if module_id else None)
    return [_test_brief(t) for t in rows]


@mcp.tool()
async def list_module_tests(ctx: Context, module_id: UUID) -> dict:
    """Тесты модуля курса: автора курса (публичные и для педагогов, принятые с курсом) и мои личные к нему."""
    key = _key(ctx)
    shared = await call(key, "assessment", "GET", "/course-tests", params={"module_id": str(module_id)})
    mine = await call(key, "assessment", "GET", "/tests", params={"module_id": str(module_id)})
    shared_ids = {t["id"] for t in shared}
    return {
        "course": [{"id": t["id"], "title": t["title"], "visibility": t["visibility"], "tasks_count": t["tasks_count"],
                    "url": link(f"/dashboard/tests/{t['id']}")} for t in shared],
        "mine": [_test_brief(t) for t in mine if t["id"] not in shared_ids],
    }


async def _get_test(key: str, test_id: UUID) -> dict:
    t = await call(key, "assessment", "GET", f"/tests/{test_id}")
    return _test_brief(t) | {
        "description": t["description"], "order_mode": t["order_mode"], "shuffle_options": t["shuffle_options"],
        "time_mode": t["time_mode"], "time_limit_min": t["time_limit_s"] / 60 if t["time_limit_s"] else None,
        "items": [{"task": str(i["task"]["number"]), "title": i["task"]["title"], "points": i["points"],
                   "solution_file": i["solution_file"]} for i in t["items"]],
    }


@mcp.tool()
async def get_test(ctx: Context, test_id: UUID) -> dict:
    """Свой тест целиком: настройки и задания (номер задачи, баллы)."""
    return await _get_test(_key(ctx), test_id)


@mcp.tool()
async def create_test(ctx: Context, test: TestFields) -> dict:
    """Создать тест из задач банка (свои или опубликованные). Назначает его ученикам педагог в интерфейсе."""
    key = _key(ctx)
    created = await call(key, "assessment", "POST", "/tests", json=await _test_body(key, test))
    return _test_brief(created)


@mcp.tool()
async def update_test(
    ctx: Context,
    test_id: UUID,
    changes: Annotated[dict[str, Any], Field(description="Что поменять — поля как у create_test; items заменяются целиком")],
) -> dict:
    """Исправить свой тест: передайте только изменённые поля. Выданные работы не меняются.
    Публичный тест в опубликованном курсе меняется только после снятия курса с публикации."""
    key = _key(ctx)
    current = await _get_test(key, test_id)
    unknown = set(changes) - set(TestFields.model_fields)
    if unknown:
        raise ToolError(f"Неизвестные поля: {', '.join(sorted(unknown))}")
    base = {f: current.get(f) for f in TestFields.model_fields if f not in ("items", "module_id")}
    base["items"] = [{k: i[k] for k in ("task", "points", "solution_file")} for i in current["items"]]
    base["module_id"] = current["module"]["id"] if current["module"] else None
    merged = TestFields.model_validate(base | changes)
    updated = await call(key, "assessment", "PUT", f"/tests/{test_id}", json=await _test_body(key, merged))
    return _test_brief(updated)
