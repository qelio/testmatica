"""Имя пользователя: фамилия, имя и (необязательно) отчество — решение №35.

Везде показывается «Фамилия Имя Отчество» (full_name собирается из частей), поэтому и списки, отсортированные
по full_name, идут по фамилии. Обращение к человеку («Привет, Мария») — по first_name."""

from pydantic import BaseModel, Field, field_validator

NAME_PART = 80


def _clean(value: str) -> str:
    return " ".join(value.split())


def compose(last_name: str, first_name: str, middle_name: str = "") -> str:
    """«Фамилия Имя Отчество» — для списков, журналов, документов."""
    return " ".join(p for p in (last_name, first_name, middle_name) if p)


class PersonName(BaseModel):
    last_name: str = Field(max_length=NAME_PART, description="Фамилия")
    first_name: str = Field(max_length=NAME_PART, description="Имя")
    middle_name: str = Field("", max_length=NAME_PART, description="Отчество — необязательно")

    @field_validator("last_name", "first_name", "middle_name", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return _clean(value) if isinstance(value, str) else value

    @field_validator("last_name", "first_name")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value:
            raise ValueError("Укажите фамилию и имя")
        return value

    @property
    def full_name(self) -> str:
        return compose(self.last_name, self.first_name, self.middle_name)


def parse_line(text: str) -> PersonName:
    """Строка списка «Фамилия Имя Отчество» (так обычно пишут списки классов) → части имени."""
    words = _clean(text).split(" ")
    if len(words) < 2:
        raise ValueError(f"«{_clean(text)}»: укажите фамилию и имя")
    return PersonName(last_name=words[0], first_name=words[1], middle_name=" ".join(words[2:]))
