"""Главная страница: схема содержимого (редактирует администратор) и начальное наполнение."""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Иконки преимуществ — из набора веба (lucide), чтобы администратор выбирал из списка.
Icon = Literal["book", "users", "calendar", "video", "chart", "shield", "sparkles", "graduation", "target", "message", "wallet", "check"]


def _href(v: str) -> str:
    v = v.strip()
    if v and not (v.startswith("/") or re.match(r"^https?://", v)):
        raise ValueError("Ссылка — адрес на сайте («/tutors») или полный адрес (https://…)")
    return v


class Hero(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field("", max_length=600)
    primary_text: str = Field("", max_length=40)
    primary_href: str = Field("", max_length=300)
    secondary_text: str = Field("", max_length=40)
    secondary_href: str = Field("", max_length=300)
    image_file_id: UUID | None = None

    _links = field_validator("primary_href", "secondary_href")(_href)


class Stat(BaseModel):
    value: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=80)


class Feature(BaseModel):
    icon: Icon = "sparkles"
    title: str = Field(min_length=1, max_length=80)
    text: str = Field("", max_length=300)


class Steps(BaseModel):
    title: str = Field("Как это работает", max_length=80)
    students: list[str] = Field(default_factory=list, max_length=6)
    teachers: list[str] = Field(default_factory=list, max_length=6)


class FeaturedTeacher(BaseModel):
    user_id: UUID
    note: str = Field("", max_length=200, description="Своя подпись вместо «коротко о себе» из профиля")


class Teachers(BaseModel):
    title: str = Field("Преподаватели", max_length=80)
    subtitle: str = Field("", max_length=300)
    items: list[FeaturedTeacher] = Field(default_factory=list, max_length=12)


class NewsBlock(BaseModel):
    title: str = Field("Новости", max_length=80)
    count: int = Field(3, ge=1, le=6)


class Faq(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    a: str = Field(min_length=1, max_length=2000)


class Contacts(BaseModel):
    text: str = Field("", max_length=300)
    email: str = Field("", max_length=120)
    phone: str = Field("", max_length=40)
    telegram: str = Field("", max_length=300)
    vk: str = Field("", max_length=300)
    address: str = Field("", max_length=200)

    _links = field_validator("telegram", "vk")(_href)


class Sections(BaseModel):
    """Какие разделы показывать."""

    stats: bool = True
    features: bool = True
    steps: bool = True
    teachers: bool = True
    news: bool = True
    faq: bool = True


class Landing(BaseModel):
    hero: Hero
    stats: list[Stat] = Field(default_factory=list, max_length=6)
    features: list[Feature] = Field(default_factory=list, max_length=9)
    steps: Steps = Field(default_factory=Steps)
    teachers: Teachers = Field(default_factory=Teachers)
    news: NewsBlock = Field(default_factory=NewsBlock)
    faq: list[Faq] = Field(default_factory=list, max_length=20)
    contacts: Contacts = Field(default_factory=Contacts)
    sections: Sections = Field(default_factory=Sections)


# Наполнение по умолчанию — из ТЗ; администратор меняет его в разделе «Главная страница».
DEFAULT_LANDING = Landing(
    hero=Hero(
        title="Учите, учитесь и находите друг друга на одной платформе",
        subtitle="ТестМатика объединяет инструменты школьного учителя, маркетплейс репетиторов и библиотеку знаний с заданиями.",
        primary_text="Начать бесплатно", primary_href="/register",
        secondary_text="Найти репетитора", secondary_href="/tutors",
    ),
    stats=[Stat(value="40 мин", label="бесплатных видеозанятий"), Stat(value="1–10", label="рейтинг репетиторов по отзывам"),
           Stat(value="0 ₽", label="для школьных учителей")],
    features=[
        Feature(icon="graduation", title="Классы и журнал", text="Группы, журнал оценок и посещаемости, КТП и расписание в одном месте."),
        Feature(icon="video", title="Видеосвязь", text="Занятия прямо в браузере: демонстрация экрана, запись, тесты на уроке."),
        Feature(icon="check", title="Задачи с автопроверкой", text="Банк задач по темам и заданиям ЕГЭ/ОГЭ, включая задачи на Python."),
        Feature(icon="users", title="Репетиторы", text="Публичные профили, отзывы, заявки учеников и наборы в мини-группы."),
        Feature(icon="chart", title="Аналитика", text="Динамика успеваемости, сравнение с классом, выгрузка в PDF и Excel."),
        Feature(icon="shield", title="Прокторинг", text="Честные тесты: показ экрана, сигналы о смене вкладки, запись."),
    ],
    steps=Steps(
        students=["Найдите репетитора или получите приглашение от учителя", "Занимайтесь по видеосвязи и решайте задания",
                  "Следите за оценками и прогрессом по заданиям ЕГЭ и ОГЭ"],
        teachers=["Создайте классы или профиль репетитора", "Собирайте тесты из банка задач и ставьте занятия в расписание",
                  "Смотрите аналитику и отмечайте пройденное по КТП"],
    ),
    teachers=Teachers(subtitle="Опытные педагоги платформы — с отзывами учеников и подтверждённым образованием."),
    faq=[
        Faq(q="Сколько это стоит?", a="Учителям и ученикам — бесплатно. Для репетиторов есть тариф «Базовый» без лимитов."),
        Faq(q="Нужно ли что-то устанавливать?", a="Нет, всё работает в браузере — на компьютере, планшете и телефоне."),
        Faq(q="Как ученику присоединиться к классу?", a="По приглашению учителя на email или по логину и паролю, которые выдаст учитель."),
    ],
    contacts=Contacts(text="Вопросы, идеи и сотрудничество — пишите, ответим."),
)
