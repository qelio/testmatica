"use client";

import "katex/dist/katex.min.css";

import { Mathematics } from "@tiptap/extension-mathematics";
import { TableKit } from "@tiptap/extension-table";
import TextAlign from "@tiptap/extension-text-align";
import { Placeholder } from "@tiptap/extensions";
import { Markdown } from "@tiptap/markdown";
import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import katex from "katex";
import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  Bold,
  Code,
  Heading2,
  Heading3,
  ImagePlus,
  Italic,
  Link2,
  List,
  ListOrdered,
  type LucideIcon,
  Paperclip,
  Quote,
  Redo2,
  Sigma,
  SquareCode,
  Strikethrough,
  Table,
  Undo2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Alert, Button, Modal } from "@/components/ui";
import { contentFileUrl, importImage, isContentFileUrl, uploadFile } from "@/lib/api";
import { AlignBlock, type Alignment, MdHeading, MdImage, MdParagraph } from "@/lib/editor-markdown";
import { errorText } from "@/lib/hooks";

const IMAGE_TYPES = "image/png,image/jpeg,image/gif,image/webp";
const FILE_TYPES = ".pdf,.doc,.docx,.odt,.rtf,.txt,.xls,.xlsx,.ods,.csv,.ppt,.pptx,.odp,.zip,.7z,.rar,.mp3,.ogg,.wav,.m4a";

type MathEdit = { latex: string; block: boolean; pos: number | null };

/**
 * Редактор текста «как в Word» для условий задач, разбора, теории и новостей.
 * Хранится по-прежнему Markdown (формулы — $…$ и $$…$$), так что все прежние тексты открываются и показываются как раньше.
 * Картинки и файлы загружаются в media с назначением «content» и вставляются постоянной ссылкой.
 */
export function RichEditor({
  value,
  onChange,
  label,
  placeholder,
  minHeight = "10rem",
  onBusyChange,
}: {
  value: string;
  onChange: (markdown: string) => void;
  label?: string;
  placeholder?: string;
  minHeight?: string;
  /** Идёт загрузка картинки или файла — форма не должна сохраняться, иначе их не будет в тексте. */
  onBusyChange?: (busy: boolean) => void;
}) {
  const [math, setMath] = useState<MathEdit | null>(null);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string>();
  const imageInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  // Последний Markdown, отданный наружу: внешнее значение меняем в редакторе, только если оно пришло не от нас.
  const emitted = useRef(value);
  const uploadRef = useRef<(files: File[], asImage: boolean) => void>(() => {});

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      // Подчёркивания в Markdown нет — не предлагаем, чтобы оно не терялось при сохранении.
      StarterKit.configure({ paragraph: false, heading: false, underline: false, link: { openOnClick: false, autolink: true } }),
      MdParagraph,
      MdHeading,
      // Картинка — в строке текста (её выравнивает абзац), размер меняется за угол; data:-картинки (из Word) переносим к себе.
      MdImage.configure({
        inline: true,
        allowBase64: true,
        resize: { enabled: true, directions: ["bottom-right", "bottom-left"], minWidth: 40, minHeight: 20, alwaysPreserveAspectRatio: true },
      }),
      TableKit.configure({ table: { resizable: false } }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      AlignBlock,
      Mathematics.configure({
        inlineOptions: { onClick: (node, pos) => setMath({ latex: node.attrs.latex, block: false, pos }) },
        blockOptions: { onClick: (node, pos) => setMath({ latex: node.attrs.latex, block: true, pos }) },
        katexOptions: { throwOnError: false },
      }),
      Placeholder.configure({ placeholder: placeholder ?? "Начните писать…" }),
      Markdown,
    ],
    content: value,
    contentType: "markdown",
    editorProps: {
      attributes: { class: "prose-tm tm-editor", style: `min-height: ${minHeight}` },
      // Картинка из буфера обмена или перетащенная — сразу загружаем и вставляем.
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files ?? []).filter((f) => f.type.startsWith("image/"));
        if (!files.length) return false;
        uploadRef.current(files, true);
        return true;
      },
      handleDrop: (_view, event) => {
        const files = Array.from((event as DragEvent).dataTransfer?.files ?? []);
        if (!files.length) return false;
        event.preventDefault();
        uploadRef.current(files, files.every((f) => f.type.startsWith("image/")));
        return true;
      },
    },
    onUpdate: ({ editor: e }) => {
      emitted.current = e.getMarkdown();
      onChange(emitted.current);
    },
  });

  // Значение сменили снаружи (сброс формы после сохранения, загрузка другой задачи).
  useEffect(() => {
    if (!editor || value === emitted.current) return;
    emitted.current = value;
    editor.commands.setContent(value, { contentType: "markdown", emitUpdate: false });
  }, [editor, value]);

  // Колбэк — в ref: форма может передавать новую функцию на каждой отрисовке.
  const busyCallback = useRef(onBusyChange);
  useEffect(() => {
    busyCallback.current = onBusyChange;
  });
  useEffect(() => {
    busyCallback.current?.(uploading > 0);
  }, [uploading]);

  // Картинки не из нашего хранилища (вставили текст с другого сайта, из Word) — переносим к себе:
  // чужой сайт часто не отдаёт картинки другим сайтам, а относительный адрес у нас вообще не откроется.
  const adopting = useRef(new Set<string>());
  useEffect(() => {
    if (!editor) return;
    const replace = (from: string, to: string | null) => {
      const { tr } = editor.state;
      const found: { pos: number; size: number; attrs: Record<string, unknown> }[] = [];
      editor.state.doc.descendants((node, pos) => {
        if (node.type.name === "image" && node.attrs.src === from) found.push({ pos, size: node.nodeSize, attrs: node.attrs });
      });
      for (const f of found.reverse()) {
        if (to) tr.setNodeMarkup(f.pos, undefined, { ...f.attrs, src: to });
        else tr.delete(f.pos, f.pos + f.size);
      }
      if (found.length) editor.view.dispatch(tr);
    };
    const adopt = () => {
      editor.state.doc.descendants((node) => {
        const src = node.type.name === "image" ? String(node.attrs.src ?? "") : "";
        if (!src || isContentFileUrl(src) || adopting.current.has(src)) return;
        adopting.current.add(src);
        const done = () => {
          adopting.current.delete(src);
          setUploading((n) => n - 1);
        };
        setUploading((n) => n + 1);
        const job: Promise<{ id: string }> = src.startsWith("data:image/")
          ? fetch(src)
              .then((r) => r.blob())
              .then((b) => uploadFile(new File([b], `картинка.${b.type.split("/")[1] || "png"}`, { type: b.type }), "content"))
          : /^https?:\/\//.test(src)
            ? importImage(src)
            : Promise.reject(new Error("relative"));
        job
          .then((f) => replace(src, contentFileUrl(f.id)))
          .catch(() => {
            replace(src, null);
            setError("Картинку с другого сайта не удалось перенести — сохраните её на компьютер и вставьте кнопкой «Картинка».");
          })
          .finally(done);
      });
    };
    adopt();
    editor.on("update", adopt);
    return () => {
      editor.off("update", adopt);
    };
  }, [editor]);

  // Загрузка — в ref: её вызывают обработчики вставки и перетаскивания, созданные вместе с редактором.
  useEffect(() => {
    uploadRef.current = (files, asImage) => {
      if (!editor) return;
      setError(undefined);
      for (const file of files) {
        setUploading((n) => n + 1);
        uploadFile(file, "content")
          .then((f) => {
            const src = contentFileUrl(f.id);
            if (asImage && file.type.startsWith("image/")) {
              editor.chain().focus().setImage({ src, alt: f.filename }).run();
            } else {
              editor
                .chain()
                .focus()
                .insertContent([
                  { type: "text", text: `📎 ${f.filename}`, marks: [{ type: "link", attrs: { href: src } }] },
                  { type: "text", text: " " },
                ])
                .run();
            }
          })
          .catch((e) => setError(errorText(e)))
          .finally(() => setUploading((n) => n - 1));
      }
    };
  }, [editor]);

  return (
    <div>
      {label && <span className="mb-1.5 block text-sm font-medium">{label}</span>}
      <div className="overflow-hidden rounded-xl border border-line bg-surface focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20">
        {editor && <Toolbar editor={editor} onMath={() => setMath({ latex: "", block: false, pos: null })} onImage={() => imageInput.current?.click()} onFile={() => fileInput.current?.click()} />}
        <div className="px-4 py-3">
          <EditorContent editor={editor} />
        </div>
        {uploading > 0 && <p className="border-t border-line px-4 py-1.5 text-xs text-fg-soft">Загружаем файл…</p>}
      </div>
      {error && (
        <div className="mt-2">
          <Alert>{error}</Alert>
        </div>
      )}
      <input
        ref={imageInput}
        type="file"
        accept={IMAGE_TYPES}
        multiple
        hidden
        onChange={(e) => {
          uploadRef.current(Array.from(e.target.files ?? []), true);
          e.target.value = "";
        }}
      />
      <input
        ref={fileInput}
        type="file"
        accept={FILE_TYPES}
        multiple
        hidden
        onChange={(e) => {
          uploadRef.current(Array.from(e.target.files ?? []), false);
          e.target.value = "";
        }}
      />
      {editor && <MathModal edit={math} onClose={() => setMath(null)} editor={editor} />}
    </div>
  );
}

function Toolbar({ editor, onMath, onImage, onFile }: { editor: Editor; onMath: () => void; onImage: () => void; onFile: () => void }) {
  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      strike: e.isActive("strike"),
      code: e.isActive("code"),
      h2: e.isActive("heading", { level: 2 }),
      h3: e.isActive("heading", { level: 3 }),
      bullet: e.isActive("bulletList"),
      ordered: e.isActive("orderedList"),
      quote: e.isActive("blockquote"),
      codeBlock: e.isActive("codeBlock"),
      link: e.isActive("link"),
      table: e.isActive("table"),
      align: (["center", "right", "justify"] as Alignment[]).find((a) => e.isActive({ textAlign: a })) ?? "left",
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
    }),
  });
  const chain = () => editor.chain().focus();

  function link() {
    const current = editor.getAttributes("link").href as string | undefined;
    const href = window.prompt("Адрес ссылки (пусто — убрать ссылку)", current ?? "https://");
    if (href === null) return;
    if (!href.trim() || href.trim() === "https://") {
      chain().extendMarkRange("link").unsetLink().run();
      return;
    }
    if (editor.state.selection.empty && !current) {
      chain().insertContent({ type: "text", text: href, marks: [{ type: "link", attrs: { href } }] }).run();
    } else {
      chain().extendMarkRange("link").setLink({ href }).run();
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-line bg-muted/50 px-1.5 py-1" role="toolbar" aria-label="Форматирование">
      <Tool icon={Bold} label="Жирный (Ctrl+B)" active={s.bold} onClick={() => chain().toggleBold().run()} />
      <Tool icon={Italic} label="Курсив (Ctrl+I)" active={s.italic} onClick={() => chain().toggleItalic().run()} />
      <Tool icon={Strikethrough} label="Зачёркнутый" active={s.strike} onClick={() => chain().toggleStrike().run()} />
      <Sep />
      <Tool icon={Heading2} label="Заголовок" active={s.h2} onClick={() => chain().toggleHeading({ level: 2 }).run()} />
      <Tool icon={Heading3} label="Подзаголовок" active={s.h3} onClick={() => chain().toggleHeading({ level: 3 }).run()} />
      <Tool icon={List} label="Маркированный список" active={s.bullet} onClick={() => chain().toggleBulletList().run()} />
      <Tool icon={ListOrdered} label="Нумерованный список" active={s.ordered} onClick={() => chain().toggleOrderedList().run()} />
      <Tool icon={Quote} label="Цитата" active={s.quote} onClick={() => chain().toggleBlockquote().run()} />
      <Sep />
      <Tool icon={AlignLeft} label="По левому краю" active={s.align === "left"} onClick={() => chain().setTextAlign("left").run()} />
      <Tool icon={AlignCenter} label="По центру" active={s.align === "center"} onClick={() => chain().setTextAlign("center").run()} />
      <Tool icon={AlignRight} label="По правому краю" active={s.align === "right"} onClick={() => chain().setTextAlign("right").run()} />
      <Tool icon={AlignJustify} label="По ширине" active={s.align === "justify"} onClick={() => chain().setTextAlign("justify").run()} />
      <Sep />
      <Tool icon={Sigma} label="Формула" onClick={onMath} />
      <Tool icon={Code} label="Код в строке" active={s.code} onClick={() => chain().toggleCode().run()} />
      <Tool icon={SquareCode} label="Блок кода" active={s.codeBlock} onClick={() => chain().toggleCodeBlock().run()} />
      <Tool icon={Table} label="Таблица" active={s.table} onClick={() => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} />
      <Tool icon={Link2} label="Ссылка" active={s.link} onClick={link} />
      <Tool icon={ImagePlus} label="Картинка (можно вставить из буфера или перетащить; размер — за уголок)" onClick={onImage} />
      <Tool icon={Paperclip} label="Прикрепить файл" onClick={onFile} />
      <Sep />
      <Tool icon={Undo2} label="Отменить (Ctrl+Z)" disabled={!s.canUndo} onClick={() => chain().undo().run()} />
      <Tool icon={Redo2} label="Повторить" disabled={!s.canRedo} onClick={() => chain().redo().run()} />
      {s.table && (
        <span className="ml-1 flex flex-wrap items-center gap-1 text-xs">
          <TextTool onClick={() => chain().addRowAfter().run()}>+ строка</TextTool>
          <TextTool onClick={() => chain().addColumnAfter().run()}>+ столбец</TextTool>
          <TextTool onClick={() => chain().deleteRow().run()}>− строка</TextTool>
          <TextTool onClick={() => chain().deleteColumn().run()}>− столбец</TextTool>
          <TextTool onClick={() => chain().deleteTable().run()}>удалить таблицу</TextTool>
        </span>
      )}
    </div>
  );
}

function Tool({ icon: Icon, label, active, disabled, onClick }: { icon: LucideIcon; label: string; active?: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()} // не теряем выделение в тексте
      onClick={onClick}
      className={`grid h-8 w-8 place-items-center rounded-lg transition-colors disabled:opacity-40 ${active ? "bg-brand/15 text-brand" : "text-fg-soft hover:bg-muted hover:text-fg"}`}
    >
      <Icon size={17} aria-hidden />
    </button>
  );
}

function TextTool({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={onClick} className="rounded-md px-1.5 py-1 text-fg-soft hover:bg-muted hover:text-fg">
      {children}
    </button>
  );
}

function Sep() {
  return <span className="mx-1 h-5 w-px bg-line" aria-hidden />;
}

/** Формула в LaTeX с живым предпросмотром; щелчок по готовой формуле в тексте открывает её здесь же. */
function MathModal({ edit, onClose, editor }: { edit: MathEdit | null; onClose: () => void; editor: Editor }) {
  return (
    <Modal open={edit !== null} onClose={onClose} title={edit?.pos != null ? "Формула" : "Вставить формулу"}>
      {edit && <MathForm key={`${edit.pos}-${edit.latex}`} edit={edit} onClose={onClose} editor={editor} />}
    </Modal>
  );
}

const EXAMPLES = ["x^2", "\\frac{a}{b}", "\\sqrt{x}", "x_1", "\\pi", "\\le", "\\ne", "\\cdot", "\\sum_{i=1}^{n}"];

function MathForm({ edit, onClose, editor }: { edit: MathEdit; onClose: () => void; editor: Editor }) {
  const [latex, setLatex] = useState(edit.latex);
  const [block, setBlock] = useState(edit.block);
  const input = useRef<HTMLTextAreaElement>(null);
  // Окно (<dialog>) при открытии ставит фокус на первую кнопку — переводим его в поле формулы.
  useEffect(() => {
    const t = requestAnimationFrame(() => input.current?.focus());
    return () => cancelAnimationFrame(t);
  }, []);
  const preview = latex.trim() ? katex.renderToString(latex, { throwOnError: false, displayMode: block }) : "";

  function save() {
    const value = latex.trim();
    const chain = editor.chain().focus();
    if (edit.pos != null) {
      if (!value) chain.deleteRange({ from: edit.pos, to: edit.pos + 1 }).run();
      else if (edit.block) chain.updateBlockMath({ latex: value, pos: edit.pos }).run();
      else chain.updateInlineMath({ latex: value, pos: edit.pos }).run();
    } else if (value) {
      if (block) chain.insertBlockMath({ latex: value }).run();
      else chain.insertInlineMath({ latex: value }).run();
    }
    onClose();
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Формула (LaTeX)</span>
        <textarea
          ref={input}
          rows={3}
          value={latex}
          onChange={(e) => setLatex(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              save();
            }
          }}
          placeholder="\frac{a+b}{2}"
          className="w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 font-mono text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
        />
      </label>
      <div className="flex flex-wrap gap-1">
        {EXAMPLES.map((x) => (
          <button key={x} type="button" onClick={() => setLatex((l) => (l ? `${l} ${x}` : x))} className="rounded-md bg-muted px-2 py-1 font-mono text-xs hover:bg-line">
            {x}
          </button>
        ))}
      </div>
      <div className="min-h-14 rounded-xl border border-dashed border-line p-3 text-center text-xl" aria-live="polite">
        {preview ? <span dangerouslySetInnerHTML={{ __html: preview }} /> : <span className="text-sm text-fg-soft">Здесь появится формула</span>}
      </div>
      {edit.pos == null && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={block} onChange={(e) => setBlock(e.target.checked)} className="accent-brand" />
          Отдельной строкой по центру
        </label>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onClose}>
          Отмена
        </Button>
        <Button type="submit">{edit.pos != null ? (latex.trim() ? "Сохранить" : "Удалить формулу") : "Вставить"}</Button>
      </div>
    </form>
  );
}
