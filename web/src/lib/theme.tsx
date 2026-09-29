"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

import { THEME_KEY as KEY } from "@/lib/theme-script";

// Тема: system — по настройке устройства; light/dark — выбор пользователя (хранится в браузере).
export type Theme = "system" | "light" | "dark";

const EVENT = "tm:theme";
const DARK = "(prefers-color-scheme: dark)";


function read(): Theme {
  try {
    const t = window.localStorage.getItem(KEY);
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

export function setTheme(theme: Theme): void {
  try {
    if (theme === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, theme);
  } catch {
    /* хранилище недоступно — тема действует до перезагрузки */
  }
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(cb: () => void): () => void {
  const mq = window.matchMedia(DARK);
  mq.addEventListener("change", cb);
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    mq.removeEventListener("change", cb);
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, read, () => "system");
}

/** Итоговая тема с учётом «системной» — для компонентов со своими цветами (редактор кода). */
export function useDarkMode(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => {
      const t = read();
      return t === "dark" || (t === "system" && window.matchMedia(DARK).matches);
    },
    () => false,
  );
}

/** Кнопка в шапке: светлая ⇄ тёмная. Пока пользователь не выбирал — тема как в системе. */
export function ThemeToggle() {
  const dark = useDarkMode();
  const Icon = dark ? Moon : Sun;
  const label = dark ? "Тёмная тема — включить светлую" : "Светлая тема — включить тёмную";
  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-fg-soft hover:bg-muted hover:text-fg"
      aria-label={label}
      title={label}
    >
      <Icon size={18} strokeWidth={1.8} aria-hidden />
    </button>
  );
}
