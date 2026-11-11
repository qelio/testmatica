"""Что и какого размера можно загружать для разных целей."""

from dataclasses import dataclass
from pathlib import PurePath

MB = 1024 * 1024

IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
DOCUMENTS = {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp"}
ARCHIVES = {".zip", ".7z", ".rar"}
CODE = {".py", ".ipynb", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".html", ".css", ".json", ".sql", ".md",
        # Школьная информатика: КуМир, Паскаль (Free/PascalABC.NET, Lazarus, Delphi), Бейсик, C++.
        ".kum", ".pas", ".pp", ".lpr", ".dpr", ".bas", ".cc", ".cxx", ".hpp"}
VIDEO = {".mp4", ".webm", ".mov"}
AUDIO = {".mp3", ".ogg", ".wav", ".m4a"}

# Эти типы браузер может показать прямо на странице; остальные отдаются только как скачивание.
INLINE = IMAGES | {".pdf"} | VIDEO | AUDIO


@dataclass(frozen=True)
class Purpose:
    max_size: int
    extensions: frozenset[str]
    label: str


PURPOSES: dict[str, Purpose] = {
    "chat_attachment": Purpose(20 * MB, frozenset(IMAGES | DOCUMENTS | ARCHIVES | CODE | AUDIO), "вложение в чат"),
    "answer": Purpose(20 * MB, frozenset(IMAGES | DOCUMENTS | ARCHIVES | CODE), "файл с ответом"),
    "material": Purpose(500 * MB, frozenset(IMAGES | DOCUMENTS | VIDEO | AUDIO | ARCHIVES), "учебный материал"),
    "avatar": Purpose(5 * MB, frozenset(IMAGES), "фото профиля"),
    # Дипломы, сертификаты, документы для верификации — только модератору и владельцу.
    "document": Purpose(20 * MB, frozenset(IMAGES | {".pdf"}), "документ"),
    # Картинки главной страницы и обложки новостей — загружает администратор, видят все.
    "site": Purpose(10 * MB, frozenset(IMAGES - {".heic"}), "картинка для сайта"),
    # Картинки и файлы внутри текста (условие задачи, разбор, теория, новости) — по постоянной ссылке
    # /files/{id}/content, её видит каждый, кому показан текст. HEIC браузеры не показывают — не принимаем.
    "content": Purpose(20 * MB, frozenset((IMAGES - {".heic"}) | DOCUMENTS | ARCHIVES | AUDIO), "картинка или файл в тексте"),
}


def extension(filename: str) -> str:
    return PurePath(filename).suffix.lower()


def is_inline(filename: str) -> bool:
    return extension(filename) in INLINE


def safe_filename(filename: str) -> str:
    """Имя без пути и управляющих символов — для Content-Disposition."""
    name = PurePath(filename.replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '"<>')
    return (name or "file")[:200]
