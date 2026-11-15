"use client";

import { python } from "@codemirror/lang-python";
import { oneDark } from "@codemirror/theme-one-dark";
import CodeMirror from "@uiw/react-codemirror";
import { CodeXml } from "lucide-react";

import { useDarkMode } from "@/lib/theme";

/** Редактор кода с подсветкой Python. readOnly — для просмотра чужих решений. */
export function CodeEditor({
  value,
  onChange,
  readOnly,
  minHeight = "200px",
  label = "Код",
  presentation,
}: {
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  minHeight?: string;
  label?: string;
  presentation?: "dark-panel";
}) {
  const dark = useDarkMode();
  const panel = presentation === "dark-panel";
  return (
    <div
      className={`overflow-hidden rounded-xl border text-sm ${panel ? "border-code-line bg-code-panel focus-within:ring-2 focus-within:ring-brand/35" : "border-line"}`}
      aria-label={label}
    >
      {panel && (
        <div className="flex items-center gap-2 border-b border-code-line px-4 py-2 font-mono text-xs font-medium text-code-label">
          <CodeXml size={16} aria-hidden="true" />
          Python
        </div>
      )}
      <CodeMirror
        value={value}
        onChange={onChange}
        readOnly={readOnly}
        editable={!readOnly}
        extensions={[python()]}
        theme={panel || dark ? oneDark : "light"}
        className={panel ? "[&_.cm-content]:py-3 [&_.cm-gutter]:min-w-9 [&_.cm-gutters]:py-3 [&_.cm-line]:px-3 [&_.cm-scroller]:leading-6" : undefined}
        minHeight={minHeight}
        basicSetup={{ foldGutter: false, highlightActiveLine: !readOnly, autocompletion: !readOnly }}
      />
    </div>
  );
}
