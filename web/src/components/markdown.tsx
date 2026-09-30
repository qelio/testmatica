"use client";

import "katex/dist/katex.min.css";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { isContentFileUrl } from "@/lib/api";

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
          a: ({ href, children }) =>
            isContentFileUrl(href) ? (
              // Файл, прикреплённый в редакторе, — плашкой (📎 в тексте ссылки уже есть).
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="tm-file inline-flex max-w-full items-center gap-1 rounded-lg border border-line bg-muted/60 px-2 py-0.5 text-sm hover:border-brand/50"
              >
                {children}
              </a>
            ) : (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          img: ({ src, alt }) =>
            // Картинки из текста — по постоянной ссылке media (без оптимизатора Next).
            // eslint-disable-next-line @next/next/no-img-element
            <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} loading="lazy" />,
        }}
      >
        {normalizeDisplayMath(text)}
      </ReactMarkdown>
    </div>
  );
}
