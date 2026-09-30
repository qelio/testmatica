"""PDF с карточками входа для учеников, которых педагог создал сам: вырезать и раздать.
Один лист A4 — до 21 карточки (при 8 и меньше — крупные); больше — на следующих листах. Оформление — «космический пропуск»."""

import io
import math
import random
from dataclasses import dataclass

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from testmatica_common.pdf import fit_text, register_fonts

# Пары «фон карточки — акцент»: пастель и насыщенный цвет той же гаммы.
PALETTE = [
    ("#EDE9FE", "#7C3AED"),
    ("#DCFCE7", "#16A34A"),
    ("#FFE4D6", "#EA580C"),
    ("#DBEAFE", "#2563EB"),
    ("#FEF3C7", "#D97706"),
    ("#FCE7F3", "#DB2777"),
    ("#CCFBF1", "#0D9488"),
]
INK = HexColor("#1F2937")
SOFT = HexColor("#6B7280")
CUT = HexColor("#9CA3AF")


@dataclass
class Card:
    full_name: str
    login: str
    password: str


def _star(c: Canvas, x: float, y: float, r: float, color) -> None:
    """Пятиконечная звёздочка."""
    p = c.beginPath()
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        angle = math.pi / 2 + i * math.pi / 5
        px, py = x + radius * math.cos(angle), y + radius * math.sin(angle)
        p.moveTo(px, py) if i == 0 else p.lineTo(px, py)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, stroke=0, fill=1)


def _planet(c: Canvas, x: float, y: float, r: float, accent) -> None:
    """Планета с кольцом: кольцо сзади, шар, кольцо спереди."""
    c.saveState()
    c.translate(x, y)
    c.rotate(-18)
    c.setStrokeColor(accent)
    c.setLineWidth(r * 0.14)
    c.ellipse(-r * 1.75, -r * 0.42, r * 1.75, r * 0.42, stroke=1, fill=0)
    c.setFillColor(accent)
    c.circle(0, 0, r, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFillAlpha(0.35)
    c.circle(-r * 0.35, r * 0.35, r * 0.28, stroke=0, fill=1)  # блик
    c.setFillAlpha(1)
    # Передняя половина кольца поверх шара.
    p = c.beginPath()
    p.arc(-r * 1.75, -r * 0.42, r * 1.75, r * 0.42, startAng=180, extent=180)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def _rocket(c: Canvas, x: float, y: float, h: float, accent) -> None:
    """Маленькая ракета, летящая вверх-вправо."""
    c.saveState()
    c.translate(x, y)
    c.rotate(-35)
    w = h * 0.34
    c.setFillColor(HexColor("#F97316"))
    flame = c.beginPath()
    flame.moveTo(-w * 0.3, 0)
    flame.lineTo(0, -h * 0.35)
    flame.lineTo(w * 0.3, 0)
    flame.close()
    c.drawPath(flame, stroke=0, fill=1)
    c.setFillColor(white)
    c.setStrokeColor(accent)
    c.setLineWidth(0.8)
    body = c.beginPath()
    body.moveTo(-w / 2, 0)
    body.lineTo(-w / 2, h * 0.62)
    body.curveTo(-w / 2, h * 0.85, 0, h, 0, h)
    body.curveTo(0, h, w / 2, h * 0.85, w / 2, h * 0.62)
    body.lineTo(w / 2, 0)
    body.close()
    c.drawPath(body, stroke=1, fill=1)
    c.setFillColor(accent)
    c.circle(0, h * 0.58, w * 0.2, stroke=0, fill=1)  # иллюминатор
    for side in (-1, 1):  # стабилизаторы
        fin = c.beginPath()
        fin.moveTo(side * w / 2, h * 0.28)
        fin.lineTo(side * w * 0.95, 0)
        fin.lineTo(side * w / 2, 0)
        fin.close()
        c.drawPath(fin, stroke=0, fill=1)
    c.restoreState()


def _name_lines(name: str, size: float, width: float, max_lines: int) -> list[tuple[str, float]]:
    """Имя в одну строку; длинное на крупной карточке — в две (фамилия и имя переносятся по словам)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if max_lines == 1 or stringWidth(name, "Round-Bold", size) <= width or " " not in name:
        return [fit_text(name, "Round-Bold", size, width)]
    size = size * 0.85
    words, first = name.split(), ""
    while words and stringWidth(f"{first} {words[0]}".strip(), "Round-Bold", size) <= width:
        first = f"{first} {words.pop(0)}".strip()
    if not first:  # первое слово само не влезает
        first = words.pop(0)
    return [fit_text(first, "Round-Bold", size, width), fit_text(" ".join(words), "Round-Bold", size, width)] if words else [
        fit_text(first, "Round-Bold", size, width)]


def _qr(c: Canvas, value: str, x: float, y: float, size: float) -> None:
    widget = QrCodeWidget(value, barLevel="M")
    x1, y1, x2, y2 = widget.getBounds()
    d = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def _field(c: Canvas, label: str, value: str, x: float, y: float, w: float, h: float, compact: bool, accent) -> None:
    """Белая плашка: подпись сверху мелко, значение моноширинным — чтобы не спутать l и 1."""
    c.setFillColor(white)
    c.setStrokeColor(accent)
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, h * 0.25, stroke=1, fill=1)
    c.setFillColor(SOFT)
    c.setFont("Round-Bold", 5.5 if compact else 6.5)
    c.drawString(x + 2 * mm, y + h - (2.3 if compact else 3) * mm, label)
    text, size = fit_text(value, "Mono-Bold", 9.5 if compact else 13, w - 4 * mm)
    c.setFillColor(INK)
    c.setFont("Mono-Bold", size)
    c.drawString(x + 2 * mm, y + (1.6 if compact else 2.2) * mm, text)


def _card(c: Canvas, card: Card, x: float, y: float, w: float, h: float, n: int, compact: bool, login_url: str) -> None:
    """login_url — адрес входа; в QR-коде — с подставленным логином."""
    bg, accent_hex = PALETTE[n % len(PALETTE)]
    accent = HexColor(accent_hex)
    pad = 2.2 * mm
    ix, iy, iw, ih = x + pad, y + pad, w - 2 * pad, h - 2 * pad
    c.setFillColor(HexColor(bg))
    c.setStrokeColor(accent)
    c.setLineWidth(1)
    c.roundRect(ix, iy, iw, ih, 4 * mm if not compact else 3 * mm, stroke=1, fill=1)

    # Космос: планета, ракета, звёзды — у каждой карточки чуть по-своему.
    rnd = random.Random(card.login)
    c.saveState()
    p = c.beginPath()
    p.roundRect(ix, iy, iw, ih, 4 * mm if not compact else 3 * mm)
    c.clipPath(p, stroke=0, fill=0)
    _planet(c, ix + iw - (8 if compact else 12) * mm, iy + ih - (6 if compact else 9) * mm, (3.2 if compact else 5) * mm, accent)
    # Звёзды — только в правом верхнем углу, вокруг планеты: там нет текста.
    px, py = ix + iw - (8 if compact else 12) * mm, iy + ih - (6 if compact else 9) * mm
    placed = 0
    while placed < (4 if compact else 6):
        sx, sy = ix + rnd.uniform(0.7, 0.97) * iw, iy + rnd.uniform(0.62 if compact else 0.66, 0.96) * ih
        if math.hypot(sx - px, sy - py) < (6 if compact else 9) * mm:
            continue  # не на планете
        _star(c, sx, sy, rnd.uniform(0.5, 1.0 if compact else 1.2) * mm, accent)
        placed += 1
    c.restoreState()

    qr = (13 if compact else 20) * mm
    text_w = iw - qr - 7 * mm
    top = iy + ih - (4.5 if compact else 6.5) * mm
    c.setFillColor(accent)
    c.setFont("Round-Bold", 6 if compact else 7.5)
    c.drawString(ix + 3 * mm, top, "ПРОПУСК В ТЕСТМАТИКУ")
    c.setFillColor(INK)
    lines = _name_lines(card.full_name, 10 if compact else 14, iw * 0.66, 2 if not compact else 1)
    step = lines[0][1] * 1.25  # межстрочный — по первой строке
    for n, (text, size) in enumerate(lines):
        c.setFont("Round-Bold", size)
        c.drawString(ix + 3 * mm, top - (5 if compact else 7.5) * mm - n * step, text)

    fh = (7.5 if compact else 10) * mm
    gap = (1.5 if compact else 2.5) * mm
    base = iy + (3 if compact else 7) * mm
    _field(c, "ПАРОЛЬ", card.password, ix + 3 * mm, base, text_w, fh, compact, accent)
    _field(c, "ЛОГИН", card.login, ix + 3 * mm, base + fh + gap, text_w, fh, compact, accent)

    qx, qy = ix + iw - qr - 2.5 * mm, iy + (2.5 if compact else 6) * mm
    c.setFillColor(white)
    c.roundRect(qx - 1 * mm, qy - 1 * mm, qr + 2 * mm, qr + 2 * mm, 1.5 * mm, stroke=0, fill=1)
    _qr(c, f"{login_url}?login={card.login}", qx, qy, qr)
    if compact:
        return
    _rocket(c, qx + qr / 2 - 2 * mm, qy + qr + 5 * mm, 9 * mm, accent)
    c.setFillColor(SOFT)
    c.setFont("Sans", 6)
    c.drawString(ix + 3 * mm, iy + 2.5 * mm, "Пароль никому не показывай. Вход — по QR-коду или на сайте.")


def _cut_lines(c: Canvas, x0: float, y0: float, cols: int, rows: int, w: float, h: float) -> None:
    """Пунктир для вырезания и ножницы у каждой линии."""
    c.setStrokeColor(CUT)
    c.setLineWidth(0.5)
    c.setDash(3, 2)
    for i in range(cols + 1):
        c.line(x0 + i * w, y0, x0 + i * w, y0 + rows * h)
    for j in range(rows + 1):
        c.line(x0, y0 + j * h, x0 + cols * w, y0 + j * h)
    c.setDash()
    c.setFillColor(CUT)
    c.setFont("Sans", 9)
    for j in range(rows + 1):
        c.drawString(x0 - 4.2 * mm, y0 + j * h - 1.2 * mm, "✂")


def render(cards: list[Card], login_url: str, title: str) -> bytes:
    register_fonts()
    compact = len(cards) > 8
    cols, rows = (3, 7) if compact else (2, 4)
    page_w, page_h = A4
    margin_x, margin_top, margin_bottom = 8 * mm, 14 * mm, 8 * mm
    w = (page_w - 2 * margin_x) / cols
    h = (page_h - margin_top - margin_bottom) / rows
    per_page = cols * rows

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    c.setTitle(title)
    c.setAuthor("ТестМатика")
    for start in range(0, len(cards), per_page):
        chunk = cards[start : start + per_page]
        c.setFillColor(SOFT)
        c.setFont("Round-Bold", 9)
        c.drawString(margin_x, page_h - 9 * mm, title)
        c.setFont("Sans", 7)
        c.drawRightString(page_w - margin_x, page_h - 9 * mm, "Вырежьте по пунктиру и раздайте ученикам")
        used_rows = (len(chunk) + cols - 1) // cols
        y_top = page_h - margin_top
        for n, card in enumerate(chunk):
            col, row = n % cols, n // cols
            _card(c, card, margin_x + col * w, y_top - (row + 1) * h, w, h, start + n, compact, login_url)
        _cut_lines(c, margin_x, y_top - used_rows * h, cols, used_rows, w, h)
        c.showPage()
    c.save()
    return buf.getvalue()
