"""Общее для PDF (reportlab): шрифты с кириллицей. Шрифты ставятся в образ пакетами Debian (см. Dockerfile).
Сервис, который делает PDF, добавляет reportlab в свои зависимости."""

from functools import cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIRS = (Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/comfortaa"))

# Имя в PDF → файл шрифта.
FONTS = {
    "Sans": "DejaVuSans.ttf",
    "Sans-Bold": "DejaVuSans-Bold.ttf",
    "Mono": "DejaVuSansMono.ttf",
    "Mono-Bold": "DejaVuSansMono-Bold.ttf",
    "Round": "Comfortaa-Regular.ttf",
    "Round-Bold": "Comfortaa-Bold.ttf",
}


@cache
def register_fonts() -> None:
    for name, filename in FONTS.items():
        path = next((d / filename for d in FONT_DIRS if (d / filename).exists()), None)
        if path is None:
            raise RuntimeError(f"Не найден шрифт {filename}: нужны пакеты fonts-dejavu-core и fonts-comfortaa")
        pdfmetrics.registerFont(TTFont(name, str(path)))


def fit_text(text: str, font: str, size: float, max_width: float, min_size: float = 6) -> tuple[str, float]:
    """Уменьшить кегль, чтобы строка влезла; если и на минимальном не влезает — обрезать с многоточием."""
    while size > min_size and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text, size
    while text and pdfmetrics.stringWidth(text + "…", font, size) > max_width:
        text = text[:-1]
    return text + "…", size
