"""Шаблоны писем. Пока — простой текст + минимальный HTML."""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class Template:
    subject: str
    text: str


TEMPLATES: dict[str, Template] = {
    "email_verification": Template(
        subject="Код подтверждения email — {code}",
        text=(
            "Здравствуйте, {name}!\n\n"
            "Ваш код подтверждения: {code}\n"
            "Код действует {ttl_minutes} минут.\n\n"
            "Если вы не регистрировались в Тестматике, просто проигнорируйте это письмо."
        ),
    ),
    "login": Template(
        subject="Код для входа — {code}",
        text=(
            "Здравствуйте, {name}!\n\n"
            "Код для входа в Тестматику: {code}\n"
            "Код действует {ttl_minutes} минут.\n\n"
            "Если вы не пытались войти, срочно смените пароль."
        ),
    ),
    "password_reset": Template(
        subject="Сброс пароля — {code}",
        text=(
            "Здравствуйте, {name}!\n\n"
            "Код для сброса пароля: {code}\n"
            "Код действует {ttl_minutes} минут.\n\n"
            "Если вы не запрашивали сброс, проигнорируйте письмо — пароль останется прежним."
        ),
    ),
}


class UnknownTemplate(Exception):
    pass


def render(template: str, params: dict) -> tuple[str, str, str]:
    """Вернуть (тема, текст, html)."""
    tpl = TEMPLATES.get(template)
    if tpl is None:
        raise UnknownTemplate(template)
    subject = tpl.subject.format(**params)
    text = tpl.text.format(**params)
    html_params = {k: escape(str(v)) for k, v in params.items()}
    html_body = escape(tpl.text).replace("\n", "<br>")
    # Подставляем экранированные значения в экранированный шаблон.
    html_body = html_body.format(**html_params)
    html = f'<div style="font-family: sans-serif; font-size: 15px; line-height: 1.5">{html_body}</div>'
    return subject, text, html
