"use client";

import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror from "@uiw/react-codemirror";
import { useSyncExternalStore } from "react";

const DARK = "(prefers-color-scheme: dark)";

function useDarkMode(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(DARK);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(DARK).matches,
    () => false,
  );
}

/** Редактор кода с подсветкой Python. readOnly — для просмотра чужих решений. */
export function CodeEditor({
  value,
  onChange,
  readOnly,
  minHeight = "200px",
  label = "Код",
}: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  minHeight?: string;
  label?: string;
}) {
  const dark = useDarkMode();
  return (
    <div className="overflow-hidden rounded-xl border border-line text-sm" aria-label={label}>
      <CodeMirror
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        editable={!readOnly}
        extensions={[python()]}
        theme={dark ? oneDark : "light"}
        minHeight={minHeight}
        basicSetup={{ foldGutter: false, highlightActiveLine: !readOnly, autocompletion: !readOnly }}
      />
    </div>
  );
}
