/** Расширения редактора, которые пишут и читают Markdown (решение №33).
 *
 * Выравнивание абзацев и заголовков — блоками `:::center … :::` (так же их понимает показ текста — remark-directive),
 * ширина картинки — в её заголовке: `![подпись](адрес "width=320")`. Всё остальное — обычный Markdown. */

import { Extension } from "@tiptap/core";
import Heading from "@tiptap/extension-heading";
import Image from "@tiptap/extension-image";
import Paragraph from "@tiptap/extension-paragraph";
import { renderTableToMarkdown, Table } from "@tiptap/extension-table";

export const ALIGNMENTS = ["left", "center", "right", "justify"] as const;
export type Alignment = (typeof ALIGNMENTS)[number];

const ALIGN_BLOCK = /^:::(left|center|right|justify)[ \t]*\n([\s\S]*?)\n:::[ \t]*(?:\n|$)/;
const IMAGE_WIDTH = /^width=(\d+)$/;

type MdNode = { type?: string; attrs?: Record<string, unknown> };

/** Обернуть выровненный абзац или заголовок в блок `:::<выравнивание>`. По левому краю — без обёртки. */
function withAlignment(node: MdNode, markdown: string): string {
  const align = node.attrs?.textAlign;
  return typeof align === "string" && align !== "left" ? `:::${align}\n${markdown}\n:::` : markdown;
}

/** Абзац: всегда остаётся абзацем (иначе абзац из одной картинки «поднимается» до картинки и теряет выравнивание). */
export const MdParagraph = Paragraph.extend({
  parseMarkdown(token, helpers) {
    return helpers.createNode("paragraph", undefined, helpers.parseInline(token.tokens ?? []));
  },
  renderMarkdown(node, helpers, ctx) {
    return withAlignment(node, this.parent?.(node, helpers, ctx) ?? "");
  },
});

export const MdHeading = Heading.extend({
  renderMarkdown(node, helpers, ctx) {
    return withAlignment(node, this.parent?.(node, helpers, ctx) ?? "");
  },
});

/** Блок `:::center … :::` → вложенные абзацы и заголовки с выравниванием. */
export const AlignBlock = Extension.create({
  name: "alignBlock",
  markdownTokenizer: {
    name: "alignBlock",
    level: "block",
    start: (src: string) => src.indexOf(":::"),
    tokenize(src, _tokens, lexer) {
      const m = ALIGN_BLOCK.exec(src);
      if (!m) return undefined;
      return { type: "alignBlock", raw: m[0], align: m[1], tokens: lexer.blockTokens(m[2]) };
    },
  },
  parseMarkdown(token, helpers) {
    return helpers
      .parseChildren(token.tokens ?? [])
      .map((n) => (n.type === "paragraph" || n.type === "heading" ? { ...n, attrs: { ...n.attrs, textAlign: token.align } } : n));
  },
});

/** Картинка в строке текста (её выравнивает абзац), с изменяемой шириной; ширина хранится в заголовке картинки. */
export const MdImage = Image.extend({
  parseMarkdown(token, helpers) {
    const m = IMAGE_WIDTH.exec(token.title ?? "");
    return helpers.createNode("image", { src: token.href, alt: token.text, title: m ? null : token.title, width: m ? Number(m[1]) : null });
  },
  renderMarkdown(node) {
    const { src, alt, width } = (node.attrs ?? {}) as { src?: string; alt?: string; width?: number };
    return `![${alt ?? ""}](${src ?? ""}${width ? ` "width=${Math.round(width)}"` : ""})`;
  },
});

type MdTableNode = { type?: string; content?: MdTableNode[]; [key: string]: unknown };

/** Таблица: в Markdown у таблицы всегда есть строка заголовка. У вставленной из Word или с сайта таблицы заголовочных
 *  ячеек нет — без этого появлялась пустая первая строка; теперь заголовком становится первая строка таблицы. */
export const MdTable = Table.extend({
  renderMarkdown(node, h) {
    const table = node as MdTableNode;
    const [first, ...rest] = table.content ?? [];
    const hasHeader = !!first?.content?.some((cell) => cell.type === "tableHeader");
    const fixed =
      first && !hasHeader ? { ...table, content: [{ ...first, content: first.content?.map((c) => ({ ...c, type: "tableHeader" })) }, ...rest] } : table;
    return renderTableToMarkdown(fixed as Parameters<typeof renderTableToMarkdown>[0], h);
  },
});

/** Ширина картинки из заголовка «width=320» — для показа текста. */
export function imageWidth(title: string | undefined): number | null {
  const m = IMAGE_WIDTH.exec(title ?? "");
  return m ? Number(m[1]) : null;
}
