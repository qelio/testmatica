// Выбор темы применяется до отрисовки (скрипт в корневом layout) — без вспышки не той темы.
// Отдельный модуль без "use client": строку использует серверный layout.

export const THEME_KEY = "tm:theme";

export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;
