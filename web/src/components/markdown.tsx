"use client";

import "katex/dist/katex.min.css";

import ReactMarkdown, { type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkDirective from "remark-directive";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { isContentFileUrl } from "@/lib/api";
import { ALIGNMENTS, imageWidth } from "@/lib/editor-markdown";

type MdNode = {
  type: string;
  name?: string;
  value?: string;
  children?: MdNode[];
  data?: Record<string, unknown>;
  position?: { start: { offset?: number }; end: { offset?: number } };
};

/** Выравнивание из редактора — блоки `:::center … :::` (remark-directive) → div с классом.
 *  Короткие директивы `:имя` в обычном тексте («x:y», «ответ:5») — возвращаем как было, текст не должен пропадать. */
function remarkAlign() {
  return (tree: MdNode, file: { value: unknown }) => {
    const source = String(file.value ?? "");
    const walk = (node: MdNode) => {
      if (node.type === "containerDirective") {
        const known = (ALIGNMENTS as readonly string[]).includes(node.name ?? "");
        node.data = { hName: "div", hProperties: { className: known ? [`tm-align-${node.name}`] : [] } };
      }
      // Узлы без детей (формулы, картинки) не трогаем: пустое поле children ломает преобразование в HTML.
      if (!node.children) return;
      node.children = node.children.map((child) => {
        if (child.type === "textDirective" || child.type === "leafDirective") {
          const { start, end } = child.position ?? { start: {}, end: {} };
          const raw = start.offset != null && end.offset != null ? source.slice(start.offset, end.offset) : `:${child.name ?? ""}`;
          return { type: "text", value: raw };
        }
        walk(child);
        return child;
      });
    };
    walk(tree);
  };
}

/** `<br>` в тексте (обычно в ячейках таблиц: «−32<br>14<br>17») — перенос строки. Остальной HTML не выполняется. */
function remarkBr() {
  return (tree: MdNode) => {
    const walk = (node: MdNode) => {
      if (!node.children) return;
      node.children = node.children.map((child) =>
        child.type === "html" && /^<br\s*\/?>$/i.test((child.value ?? "").trim()) ? { type: "break" } : (walk(child), child),
      );
    };
    walk(tree);
  };
}

/** Строка из одной формулы «$$…$$» — выносная формула по центру (remark-math ждёт $$ на отдельных строках). */
function normalizeDisplayMath(text: string): string {
  return text.replace(/^[ \t]*\$\$([^\n]+?)\$\$[ \t]*$/gm, (_, formula: string) => `$$\n${formula.trim()}\n$$`);
}

/** Свои элементы — одни и те же при каждой отрисовке: иначе React пересоздаёт <img> на каждое обновление страницы
 *  (например, после «Отправить в публичный банк»), и картинка грузится заново. */
const COMPONENTS: Components = {
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
  img: ({ src, alt, title }) => {
    // Ширина, заданная в редакторе, — в заголовке картинки («width=320»).
    const width = imageWidth(title);
    return (
      // Картинки из текста — по постоянной ссылке media (без оптимизатора Next).
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={typeof src === "string" ? src : undefined}
        alt={alt ?? ""}
        title={width ? undefined : title}
        width={width ?? undefined}
        loading="lazy"
        className="inline-block"
      />
    );
  },
};

const REMARK = [remarkGfm, remarkMath, remarkDirective, remarkAlign, remarkBr];
const REHYPE = [rehypeKatex];

/** Текст материала: Markdown + таблицы + формулы ($…$ и $$…$$). Сырой HTML не выполняется. */
export function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-tm">
      <ReactMarkdown remarkPlugins={REMARK} rehypePlugins={REHYPE} components={COMPONENTS}>
        {normalizeDisplayMath(text)}
      </ReactMarkdown>
    </div>
  );
}
