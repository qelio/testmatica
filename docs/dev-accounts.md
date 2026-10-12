# Тестовые аккаунты (только локальный Docker)

Созданы для ручной проверки на локальном стенде (`make up`). В облаке и на проде их нет и быть не должно.
Код второго фактора при входе приходит на почту — смотреть в Mailpit: http://localhost:8025

| Роль          | Логин (email)                | Пароль         |
|---------------|------------------------------|----------------|
| Администратор | admin@testmatica.local       | admin-pass-1   |
| Модератор     | moderator@testmatica.local   | mod-pass-1     |
| Педагог       | maria@example.com            | maria-pass-1   |
| Педагог 2     | petr@example.com             | petr-pass-1    |
| Ученица       | olya@example.com             | olya-pass-1    |

Новый аккаунт с нужной ролью:

```bash
docker compose exec identity python -m app.cli create-user --email <email> --last-name "<Фамилия>" --first-name "<Имя>" --role <student|teacher|moderator|admin>
```
