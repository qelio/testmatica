// Часовые пояса России и соседей — чаще всего нужные (личный кабинет, карточка пользователя в админке).
export const ZONES: [string, string][] = [
  ["Europe/Kaliningrad", "Калининград (UTC+2)"],
  ["Europe/Moscow", "Москва (UTC+3)"],
  ["Europe/Samara", "Самара (UTC+4)"],
  ["Asia/Yekaterinburg", "Екатеринбург (UTC+5)"],
  ["Asia/Omsk", "Омск (UTC+6)"],
  ["Asia/Novosibirsk", "Новосибирск (UTC+7)"],
  ["Asia/Krasnoyarsk", "Красноярск (UTC+7)"],
  ["Asia/Irkutsk", "Иркутск (UTC+8)"],
  ["Asia/Yakutsk", "Якутск (UTC+9)"],
  ["Asia/Vladivostok", "Владивосток (UTC+10)"],
  ["Asia/Magadan", "Магадан (UTC+11)"],
  ["Asia/Kamchatka", "Камчатка (UTC+12)"],
  ["Europe/Minsk", "Минск (UTC+3)"],
  ["Asia/Almaty", "Алматы (UTC+5)"],
];

/** Список для выбора: текущий пояс добавляется, если его нет среди частых. */
export function zonesWith(current: string | null | undefined): [string, string][] {
  return !current || ZONES.some(([z]) => z === current) ? ZONES : [[current, current], ...ZONES];
}
