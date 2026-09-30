"""Выгрузка аналитики в Excel и PDF (ТЗ: «Экспорт в PDF / Excel», тариф «Базовый»)."""

import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from testmatica_common.pdf import register_fonts

from .schemas import GroupReport, Stats, StudentReport, Summary

HEADER_FILL = PatternFill("solid", fgColor="EEF2FF")
BRAND = colors.HexColor("#4F46E5")


def _avg(v: float | None) -> str:
    return f"{v:.2f}".replace(".", ",") if v is not None else "—"


def _pct(v: float | None) -> str:
    return f"{round(v * 100)}%" if v is not None else "—"


def _period(a: date, b: date) -> str:
    return f"{a:%d.%m.%Y} — {b:%d.%m.%Y}"


# ---------- Excel ----------


def _sheet(wb: Workbook, title: str, header: list[str], rows: list[list], widths: list[int], first: bool = False):
    ws = wb.active if first else wb.create_sheet()
    ws.title = title[:31]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    return ws


def _save(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _num(v: float | None):
    return round(v, 2) if v is not None else None


def group_xlsx(r: GroupReport) -> bytes:
    wb = Workbook()
    _sheet(wb, "Ученики", ["Ученик", "Средний балл", "Отклонение от класса", "Оценок", "Посещаемость, %", "Пропуски", "Опоздания"], [
        [s.full_name, _num(s.stats.average), _num(s.delta), s.stats.grades_count,
         round(s.stats.attendance_rate * 100) if s.stats.attendance_rate is not None else None,
         s.stats.absent + s.stats.sick, s.stats.late]
        for s in r.students
    ] + [[f"Класс: {r.title}", _num(r.stats.average), None, r.stats.grades_count,
          round(r.stats.attendance_rate * 100) if r.stats.attendance_rate is not None else None, r.stats.absent + r.stats.sick, r.stats.late]],
        [32, 14, 20, 10, 16, 11, 11], first=True)
    _sheet(wb, "По неделям", ["Неделя (пн)", "Средний балл", "Посещаемость, %"], [
        [t.week, _num(t.average), round(t.attendance_rate * 100) if t.attendance_rate is not None else None] for t in r.trend or []
    ], [14, 14, 16])
    _sheet(wb, "Пропуски по дням", ["День", "Отметок", "Пропусков", "Доля пропусков, %"], [
        [h.day, h.marked, h.missed, round(h.rate * 100)] for h in r.heatmap or []
    ], [14, 10, 12, 18])
    _sheet(wb, "Оценки", ["Оценка", "Сколько"], [[v, c] for v, c in (r.distribution or {}).items()], [10, 10])
    return _save(wb)


def student_xlsx(r: StudentReport) -> bytes:
    wb = Workbook()
    _sheet(wb, "По предметам", ["Предмет", "Средний балл", "Средний по группе", "Оценок", "Посещаемость, %"], [
        [s.subject, _num(s.stats.average), _num(s.class_average), s.stats.grades_count,
         round(s.stats.attendance_rate * 100) if s.stats.attendance_rate is not None else None] for s in r.subjects
    ], [24, 14, 18, 10, 16], first=True)
    _sheet(wb, "Оценки", ["Дата", "Предмет", "Оценка", "Тип", "Комментарий"], [
        [g.at.replace(tzinfo=None), g.subject, g.value, g.grade_type, g.comment] for g in r.grades or []
    ], [18, 20, 8, 20, 50])
    return _save(wb)


def summary_xlsx(r: Summary) -> bytes:
    wb = Workbook()
    _sheet(wb, "Сводная ведомость", ["Класс / группа", "Учеников", "Средний балл", "Оценок", "Посещаемость, %", "Пропуски", "Средний ниже 3"], [
        [s.title, s.students, _num(s.stats.average), s.stats.grades_count,
         round(s.stats.attendance_rate * 100) if s.stats.attendance_rate is not None else None, s.stats.absent + s.stats.sick, s.below_three]
        for s in r.rows
    ], [30, 10, 14, 10, 16, 11, 16], first=True)
    return _save(wb)


# ---------- PDF ----------


def _styles():
    register_fonts()
    return {
        "h1": ParagraphStyle("h1", fontName="Round-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#111827")),
        "sub": ParagraphStyle("sub", fontName="Sans", fontSize=9, leading=12, textColor=colors.HexColor("#6B7280")),
        "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4),
        "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.5, leading=10.5),
    }


def _table(header: list[str], rows: list[list[str]], widths: list[float], highlight: list[int] | None = None) -> Table:
    t = Table([header, *rows], colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, 0), "Sans-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Sans", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2FF")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3730A3")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row in highlight or []:
        style.append(("TEXTCOLOR", (0, row), (-1, row), colors.HexColor("#B91C1C")))
    t.setStyle(TableStyle(style))
    return t


def _bars(values: dict[int, int]) -> Drawing:
    """Распределение оценок горизонтальными полосками."""
    width, row = 110 * mm, 6 * mm
    top = max(values.values()) or 1
    d = Drawing(width, row * len(values))
    for i, (grade, count) in enumerate(sorted(values.items())):  # снизу вверх: 1 внизу, 5 сверху
        y = i * row
        d.add(String(0, y + 1.5 * mm, str(grade), fontName="Sans-Bold", fontSize=9))
        bar = (width - 25 * mm) * count / top
        d.add(Rect(8 * mm, y + 1 * mm, max(bar, 0.5), row - 2 * mm, fillColor=BRAND if count else colors.white, strokeColor=None))
        d.add(String(10 * mm + bar, y + 1.5 * mm, str(count), fontName="Sans", fontSize=8.5, fillColor=colors.HexColor("#374151")))
    return d


def _doc(story, title: str, landscape_mode: bool = False) -> bytes:
    buf = io.BytesIO()
    size = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=title, author="ТестМатика")
    doc.build(story)
    return buf.getvalue()


def _stats_line(s: Stats) -> str:
    return (f"Средний балл: <b>{_avg(s.average)}</b> · оценок: {s.grades_count} · посещаемость: <b>{_pct(s.attendance_rate)}</b>"
            f" · пропусков: {s.absent + s.sick} · опозданий: {s.late}")


def group_pdf(r: GroupReport) -> bytes:
    st = _styles()
    story = [
        Paragraph(f"Аналитика: {r.title}", st["h1"]),
        Paragraph(f"{_period(r.period_from, r.period_to)}{' · ' + r.subject if r.subject else ''}", st["sub"]),
        Spacer(1, 4 * mm),
        Paragraph(_stats_line(r.stats), st["cell"]),
        Paragraph("Ученики", st["h2"]),
    ]
    rows = [[s.full_name, _avg(s.stats.average), (f"{s.delta:+.2f}".replace(".", ",") if s.delta is not None else "—"),
             str(s.stats.grades_count), _pct(s.stats.attendance_rate), str(s.stats.absent + s.stats.sick)] for s in r.students]
    below = [i + 1 for i, s in enumerate(r.students) if s.delta is not None and s.delta < 0]
    story.append(_table(["Ученик", "Средний", "От класса", "Оценок", "Посещаемость", "Пропуски"], rows,
                        [62 * mm, 20 * mm, 22 * mm, 18 * mm, 26 * mm, 20 * mm], highlight=below))
    story.append(Paragraph("Красным — ниже среднего по классу.", st["sub"]))
    if r.distribution:
        story += [Paragraph("Распределение оценок", st["h2"]), _bars(r.distribution)]
    if r.trend:
        story += [Paragraph("Динамика по неделям", st["h2"]),
                  _table(["Неделя с", "Средний балл", "Посещаемость"],
                         [[f"{t.week:%d.%m}", _avg(t.average), _pct(t.attendance_rate)] for t in r.trend], [30 * mm, 30 * mm, 30 * mm])]
    worst = sorted((h for h in r.heatmap or [] if h.missed), key=lambda h: -h.rate)[:10]
    if worst:
        story += [Paragraph("Дни с наибольшей долей пропусков", st["h2"]),
                  _table(["День", "Пропусков", "Доля"], [[f"{h.day:%d.%m.%Y}", f"{h.missed} из {h.marked}", _pct(h.rate)] for h in worst],
                         [30 * mm, 30 * mm, 30 * mm])]
    return _doc(story, f"Аналитика — {r.title}")


def student_pdf(r: StudentReport) -> bytes:
    st = _styles()
    story = [
        Paragraph(f"Аналитика: {r.full_name}", st["h1"]),
        Paragraph(_period(r.period_from, r.period_to), st["sub"]),
        Spacer(1, 4 * mm),
        Paragraph(_stats_line(r.stats), st["cell"]),
        Paragraph("По предметам", st["h2"]),
        _table(["Предмет", "Средний", "Средний по группе", "Оценок", "Посещаемость"],
               [[s.subject, _avg(s.stats.average), _avg(s.class_average), str(s.stats.grades_count), _pct(s.stats.attendance_rate)]
                for s in r.subjects], [50 * mm, 22 * mm, 34 * mm, 20 * mm, 28 * mm]),
    ]
    if r.trend:
        story += [Paragraph("Динамика по неделям", st["h2"]),
                  _table(["Неделя с", "Средний балл", "Посещаемость"],
                         [[f"{t.week:%d.%m}", _avg(t.average), _pct(t.attendance_rate)] for t in r.trend], [30 * mm, 30 * mm, 30 * mm])]
    if r.grades:
        story += [Paragraph("Оценки", st["h2"]),
                  _table(["Дата", "Предмет", "Оценка", "Тип", "Комментарий"],
                         [[f"{g.at:%d.%m.%Y}", g.subject or "—", str(g.value), g.grade_type, Paragraph(g.comment, st["cell"])]
                          for g in r.grades], [22 * mm, 30 * mm, 14 * mm, 28 * mm, 86 * mm])]
    return _doc(story, f"Аналитика — {r.full_name}")


def summary_pdf(r: Summary) -> bytes:
    st = _styles()
    rows = [[s.title, str(s.students), _avg(s.stats.average), str(s.stats.grades_count), _pct(s.stats.attendance_rate),
             str(s.stats.absent + s.stats.sick), str(s.below_three)] for s in r.rows]
    rows.append(["Всего", "", _avg(r.total.average), str(r.total.grades_count), _pct(r.total.attendance_rate),
                 str(r.total.absent + r.total.sick), ""])
    story = [
        Paragraph("Сводная ведомость", st["h1"]),
        Paragraph(_period(r.period_from, r.period_to), st["sub"]),
        Spacer(1, 5 * mm),
        _table(["Класс / группа", "Учеников", "Средний", "Оценок", "Посещаемость", "Пропуски", "Средний ниже 3"], rows,
               [80 * mm, 22 * mm, 24 * mm, 22 * mm, 30 * mm, 24 * mm, 32 * mm]),
    ]
    return _doc(story, "Сводная ведомость", landscape_mode=True)
