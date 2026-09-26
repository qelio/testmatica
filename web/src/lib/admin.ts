// Подписи для админ-панели.

export const USER_STATUS = {
  active: { text: "активен", tone: "ok" },
  pending_verification: { text: "не подтвердил email", tone: "neutral" },
  banned: { text: "заблокирован", tone: "warn" },
  deleted: { text: "удалён", tone: "warn" },
} as const;

// События аудита, которые чаще всего нужны администратору. Остальные показываются как есть.
export const EVENT_LABELS: Record<string, string> = {
  "identity.user.registered": "Регистрация",
  "identity.user.logged_in": "Вход",
  "identity.user.login_failed": "Неудачная попытка входа",
  "identity.user.updated": "Профиль изменён",
  "identity.user.edited_by_admin": "Данные изменены администратором",
  "identity.user.roles_changed": "Роли изменены",
  "identity.user.banned": "Заблокирован",
  "identity.user.unbanned": "Разблокирован",
  "identity.user.deleted": "Удалён",
  "identity.user.restored": "Восстановлен",
  "identity.user.anonymized": "Данные обезличены",
  "identity.user.password_reset": "Сменил пароль",
  "identity.user.password_reset_by_admin": "Пароль сброшен администратором",
  "identity.session.token_reuse_detected": "Подозрение на кражу сессии",
  "billing.payment.succeeded": "Оплата прошла",
  "billing.payment.failed": "Оплата не прошла",
  "billing.subscription.changed": "Подписка изменилась",
  "billing.subscription.granted": "Подписка подключена администратором",
  "billing.settings.updated": "Настройки платформы изменены",
  "moderation.decision.made": "Решение модератора",
  "schedule.lesson.created": "Занятия созданы",
  "schedule.lesson.cancelled": "Занятия отменены",
  "classroom.link.created": "Ученик привязан к педагогу",
  "classroom.group.created": "Группа создана",
  "assessment.assignment.created": "Тест назначен",
  "academic.grade.created": "Оценка поставлена",
  "marketplace.deal.agreed": "Договорились",
  "marketplace.review.submitted": "Отзыв отправлен",
  "video.room.started": "Видеозанятие началось",
};

export const AUDIT_PREFIXES: [string, string][] = [
  ["", "Все события"],
  ["identity.", "Аккаунты и входы"],
  ["billing.", "Оплата и подписки"],
  ["moderation.", "Модерация"],
  ["classroom.", "Классы и ученики"],
  ["schedule.", "Расписание"],
  ["assessment.", "Задачи и тесты"],
  ["academic.", "Журнал и КТП"],
  ["marketplace.", "Маркетплейс"],
  ["video.", "Видеосвязь"],
  ["chat.", "Чаты"],
  ["content.", "Библиотека"],
];

export function eventLabel(type: string): string {
  return EVENT_LABELS[type] ?? type;
}
