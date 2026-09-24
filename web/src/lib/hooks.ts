"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./api";

export function errorText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Что-то пошло не так";
}

/** Загрузить данные при открытии экрана и при изменении deps; reload() — перезагрузить после изменений. */
export function useLoad<T>(loader: () => Promise<T>, deps: readonly unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>();
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  });

  const reload = useCallback(async () => {
    try {
      setData(await loaderRef.current());
      setError(undefined);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  const key = JSON.stringify(deps);
  useEffect(() => {
    reload();
  }, [reload, key]);

  return { data, error, reload, setData };
}
