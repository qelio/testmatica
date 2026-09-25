"use client";

import "katex/dist/katex.min.css";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

/** Строка из одной формулы «$$…$$» — выносная формула по центру (remark-math ждёт $$ на отдельных строках). */
function normalizeDisplayMath(text: string): string {
  return text.replace(/^[ \t]*\$\$([^\n]+?)\$\$[ \t]*$/gm, (_, formula: string) => `$$\n${formula.trim()}\n$$`);
}

/** Текст материала: Markdown + таблицы + формулы ($…$ и $$…$$). Сырой HTML не выполняется. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-tm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {normalizeDisplayMath(text)}
      </ReactMarkdown>
    </div>
  );
}
