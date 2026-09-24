// Куда вернуть пользователя после входа или регистрации (например, на страницу приглашения).
// Хранится в sessionStorage вкладки; страница-адресат сама очищает его, когда дело сделано.

const KEY = "tm_next";

export function rememberNext(path: string) {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {}
}

export function nextPath(): string {
  try {
    const path = sessionStorage.getItem(KEY);
    if (path && path.startsWith("/") && !path.startsWith("//")) return path;
  } catch {}
  return "/dashboard";
}

export function clearNext() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {}
}
