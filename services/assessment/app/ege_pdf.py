"""Разбор печатного варианта «РЕШУ ЕГЭ» с сохранением порядка строк и картинок."""

import base64
import ctypes
import re
from contextlib import closing
from dataclasses import dataclass, field
from io import BytesIO
from threading import Lock

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50
MAX_IMAGES_BYTES = 12 * 1024 * 1024
TASK = re.compile(r"^(\d{1,3})\.\s+(.+)$")
TYPED_TASK = re.compile(r"^Тип\s+([А-Яа-яЁё]?\d+)(?:\s+№\s*(\d+))?(?:\s+i)?$", re.IGNORECASE)
SOLUTION = re.compile(r"^Решение\s*[.:]\s*(.*)$", re.IGNORECASE)
ANSWER = re.compile(r"^О\s*т\s*в\s*е\s*т\s*[:.]\s*(.*)$", re.IGNORECASE)
CHROME = re.compile(r"^(?:\d{1,2}\.\d{2}\.\d{2,4},\s*\d{1,2}:\d{2}\b|(?:https?://)?\S*sdamgia\.ru/|\d+\s*/\s*\d+$)")
MONOSPACE = (b"menlo", b"consolas", b"courier", b"mono", b"code")
SOURCE = re.compile(r"(?:https?://)?((?:[a-z0-9-]+-)?(?:ege|oge)\.sdamgia\.ru)/(test|problem)\?id=(\d+)", re.IGNORECASE)
PDF_LOCK = Lock()  # PDFium нельзя вызывать параллельно даже для разных документов.


class InvalidVariant(ValueError):
    pass


@dataclass
class Line:
    text: str
    x: float
    y: float
    kind: str = "text"
    bold: bool = False
    right: float = 0


@dataclass
class Draft:
    number: int
    title: str
    statement: list[Line] = field(default_factory=list)
    explanation: list[Line] = field(default_factory=list)
    answer: str = ""
    source_url: str = ""


def _lines(page):
    with closing(page.get_textpage()) as text_page:
        if text_page.count_chars() > 30_000:
            raise InvalidVariant("На одной из страниц слишком много текста")
        font = ctypes.create_string_buffer(256)
        chars = []
        for index in range(text_page.count_chars()):
            char = chr(pdfium_c.FPDFText_GetUnicode(text_page, index))
            if char in "\r\n":
                if chars:
                    yield _line(text_page, font, chars)
                    chars = []
            elif char != "\x00":
                chars.append((index, char))
        if chars:
            yield _line(text_page, font, chars)


def _line(text_page, font, chars):
    index = next((index for index, char in chars if not char.isspace()), chars[0][0])
    x, bottom, _, top = text_page.get_charbox(index)
    size = pdfium_c.FPDFText_GetFontInfo(text_page, index, font, len(font), None)
    name = font.value.lower() if 0 < size <= len(font) else b""
    kind = "code" if any(part in name for part in MONOSPACE) else "text"
    last = next((index for index, char in reversed(chars) if not char.isspace()), index)
    right = text_page.get_charbox(last)[2]
    return Line("".join(char for _, char in chars).strip(), x, (bottom + top) / 2, kind, b"bold" in name, right)


def _links(page):
    index = ctypes.c_int()
    link = pdfium_c.FPDF_LINK()
    while pdfium_c.FPDFLink_Enumerate(page, ctypes.byref(index), ctypes.byref(link)):
        action = pdfium_c.FPDFLink_GetAction(link)
        rect = pdfium_c.FS_RECTF()
        buffer = ctypes.create_string_buffer(2048)
        if not action or not pdfium_c.FPDFLink_GetAnnotRect(link, ctypes.byref(rect)):
            continue
        size = pdfium_c.FPDFAction_GetURIPath(page.pdf, action, buffer, len(buffer))
        if 0 < size <= len(buffer):
            url = buffer.value.decode("ascii", errors="ignore")
            if re.fullmatch(r"https://(?:[a-z0-9-]+-)?(?:ege|oge)\.sdamgia\.ru/(?:problem|get_file)\?id=\d+", url):
                yield rect, url


def _merge_bounds(boxes, gap=2):
    groups = []
    for left, bottom, right, top in boxes:
        for index in range(len(groups) - 1, -1, -1):
            x0, y0, x1, y1 = groups[index]
            if left <= x1 + gap and right >= x0 - gap and bottom <= y1 + gap and top >= y0 - gap:
                left, bottom, right, top = min(left, x0), min(bottom, y0), max(right, x1), max(top, y1)
                groups.pop(index)
        groups.append((left, bottom, right, top))
    return groups


def _figure_bounds(page):
    width, height = page.get_size()
    grid, drawings = [], []
    rgba = [ctypes.c_uint() for _ in range(4)]
    channels = [ctypes.byref(channel) for channel in rgba]
    for obj in page.get_objects(max_depth=1):
        left, bottom, right, top = obj.get_bounds()
        if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            yield left, bottom, right, top
        if obj.type != pdfium_c.FPDF_PAGEOBJ_PATH or bottom < 20 or top > height - 20:
            continue
        w, h = right - left, top - bottom
        if w > width * 0.9 or min(w, h) < 0.2:
            continue
        if not pdfium_c.FPDFPageObj_GetFillColor(obj, *channels):
            continue
        red, green, blue, alpha = (channel.value for channel in rgba)
        if alpha >= 70 and max(red, green, blue) - min(red, green, blue) >= 30 and min(w, h) > 1:
            drawings.append((left, bottom, right, top))
        elif alpha >= 150 and min(w, h) <= 2 and max(w, h) >= 10:
            grid.append((left, bottom, right, top))
    figures = [
        (left - 1, bottom - 1, right + 1, top + 1)
        for left, bottom, right, top in _merge_bounds(grid)
        if right - left >= 45 and top - bottom >= 12
    ]
    figures.extend(
        (left - 15, bottom - 15, right + 15, top + 15)
        for left, bottom, right, top in _merge_bounds(drawings, gap=8)
        if right - left >= 45 and top - bottom >= 25
    )
    yield from _merge_bounds(figures, gap=0)


def _images(page, images, size):
    width, height = page.get_size()
    for left, bottom, right, top in _figure_bounds(page):
        left, bottom = max(left, 0), max(bottom, 0)
        right, top = min(right, width), min(top, height)
        if right - left < 5 or top - bottom < 5:
            continue
        if len(images) >= 100:
            raise InvalidVariant("В документе слишком много картинок")
        scale = min(2, 1600 / max(right - left, top - bottom))
        with closing(page.render(scale=scale, crop=(left, bottom, width - right, height - top), may_draw_forms=False)) as bitmap:
            buffer = BytesIO()
            bitmap.to_pil().save(buffer, format="PNG")
        data = buffer.getvalue()
        size += len(data)
        if size > MAX_IMAGES_BYTES:
            raise InvalidVariant("Картинки из PDF занимают слишком много места")
        index = len(images)
        images.append(base64.b64encode(data).decode("ascii"))
        yield Line(f"![Иллюстрация из PDF](ege-pdf-image-{index})", left, (bottom + top) / 2, "image"), size, (left, bottom, right, top)


def _markdown(lines):
    blocks, prose, code = [], [], []
    left = min((line.x for line in lines if line.kind == "text"), default=0)

    def flush_prose():
        if prose:
            text = " ".join(prose).replace("\u2010 ", "").replace("\u00ad", "")
            blocks.append(re.sub(r"([\\`*_[\]<>$])", r"\\\1", text))
            prose.clear()

    def flush_code():
        if code:
            start = min(x for x, _ in code)
            body = "\n".join(" " * (round((x - start) / 5.4) if x > start else 0) + text for x, text in code)
            blocks.append(f"```\n{body}\n```")
            code.clear()

    for line in lines:
        if line.kind == "code":
            flush_prose()
            code.append((line.x, line.text))
            continue
        flush_code()
        if line.kind in ("image", "link"):
            flush_prose()
            blocks.append(line.text)
        else:
            if line.x > left + 12 or line.text.startswith(("— ", "– ")):
                flush_prose()
            prose.append(line.text)
    flush_prose()
    flush_code()
    return "\n\n".join(blocks)


def _answer_value(value: str) -> str:
    if "&" in value:
        return " ".join("".join(part.split()) for part in value.split("&")).strip()
    return value.strip()


def parse_variant(data: bytes) -> dict:
    drafts, images = [], []
    draft = None
    in_solution = False
    variant = ""
    source_url = ""
    source_name = "РЕШУ ОГЭ/ЕГЭ"
    image_size = 0
    pending_answer = False
    number_x = None
    bold_numbers = False
    try:
        with PDF_LOCK, pdfium.PdfDocument(data) as document:
            if len(document) > MAX_PAGES:
                raise InvalidVariant(f"В PDF должно быть не более {MAX_PAGES} страниц")
            for page_index in range(len(document)):
                with closing(document[page_index]) as page:
                    if max(page.get_size()) > 2000 or page.get_rotation():
                        raise InvalidVariant("Страница PDF имеет неподдерживаемый размер или поворот")
                    lines = []
                    for line in _lines(page):
                        if not source_url and CHROME.match(line.text):
                            source = SOURCE.search(line.text)
                            if source:
                                host, path, source_id = source.groups()
                                source_url = f"https://{host}/{path}?id={source_id}"
                                source_name = "РЕШУ ОГЭ" if host.lower().endswith("oge.sdamgia.ru") else "РЕШУ ЕГЭ"
                        if line.text and not CHROME.match(line.text):
                            lines.append(line)
                    links = list(_links(page))
                    for line in lines:
                        for rect, url in links:
                            if "/get_file?" in url and rect.bottom - 2 <= line.y <= rect.top + 2 and abs(line.x - rect.left) < 6:
                                line.text = f"[{line.text}]({url})"
                                line.kind = "link"
                                break
                    for line, image_size, (left, bottom, right, top) in _images(page, images, image_size):
                        lines = [
                            item for item in lines
                            if not (item.kind == "text" and left <= item.x <= item.right <= right and bottom <= item.y <= top)
                        ]
                        lines.append(line)
                    for line in sorted(lines, key=lambda item: -item.y):
                        if re.search(r"РЕШУ (?:ЕГЭ|ОГЭ)", line.text) and "Вариант" in line.text and line.kind == "text":
                            source_name = "РЕШУ ОГЭ" if "РЕШУ ОГЭ" in line.text else "РЕШУ ЕГЭ"
                            match = re.search(r"Вариант\s*№\s*(\d+)", line.text)
                            if match:
                                variant = match[1]
                            continue
                        task = TASK.match(line.text) if line.kind == "text" else None
                        at_number_indent = number_x is None or abs(line.x - number_x) <= 4
                        if (
                            task and int(task[1]) == len(drafts) + 1 and at_number_indent
                            and (draft is None or (line.bold if bold_numbers else in_solution))
                        ):
                            number = int(task[1])
                            if draft is None:
                                number_x, bold_numbers = line.x, line.bold
                            if len(drafts) >= 100:
                                raise InvalidVariant("В одном PDF должно быть не более 100 задач")
                            draft = Draft(number, f"{source_name} · вариант {variant} · задача {number}" if variant else f"{source_name} · задача {number}")
                            drafts.append(draft)
                            in_solution = pending_answer = False
                            heading = TYPED_TASK.fullmatch(task[2])
                            if heading:
                                draft.title = f"Тип {heading[1]}"
                                if heading[2]:
                                    draft.source_url = next(
                                        (url for _, url in links if url.endswith(f"/problem?id={heading[2]}")),
                                        "",
                                    )
                                continue
                            line.text = task[2]
                        if draft is None:
                            continue
                        solution = SOLUTION.match(line.text) if line.kind == "text" else None
                        answer = ANSWER.match(line.text) if line.kind == "text" else None
                        if solution:
                            in_solution = True
                            pending_answer = False
                            line.text = solution[1]
                        if answer:
                            in_solution = True
                            value = answer[1].strip().removesuffix(".")
                            if value and not draft.answer:
                                draft.answer = _answer_value(value)
                            pending_answer = not value and not draft.answer
                            continue
                        if pending_answer and line.kind == "text" and re.fullmatch(r"[+−\-\d\s&.,]+", line.text):
                            draft.answer = _answer_value(line.text)
                            pending_answer = False
                            continue
                        pending_answer = False
                        if line.text:
                            (draft.explanation if in_solution else draft.statement).append(line)
    except pdfium.PdfiumError as exc:
        raise InvalidVariant("Не удалось прочитать PDF. Проверьте, что файл открывается и не защищён паролем") from exc
    if not drafts:
        raise InvalidVariant("Задачи не найдены. Загрузите печатный PDF варианта «РЕШУ ЕГЭ» с выделяемым текстом")
    return {
        "tasks": [
            {"number": task.number, "title": task.title, "statement": _markdown(task.statement),
             "answer": task.answer, "explanation": _markdown(task.explanation),
             "source_url": task.source_url or source_url or ("https://oge.sdamgia.ru/" if source_name == "РЕШУ ОГЭ" else "https://ege.sdamgia.ru/"),
             "source_name": source_name}
            for task in drafts
        ],
        "images": images,
    }
