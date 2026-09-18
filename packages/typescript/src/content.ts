/** Explicit content wrapper for text that is already HTML. */
export class HTML {
  constructor(readonly value: string) {}

  toString(): string {
    return this.value;
  }
}

/** Explicit content wrapper for Markdown text. */
export class Markdown {
  constructor(readonly value: string) {}

  toString(): string {
    return this.value;
  }
}

export type RichText = string | HTML | Markdown;

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeLink(href: string): boolean {
  const value = href.trim();
  const compact = value.replace(/[\u0000-\u0020]/gu, "");
  if (/^(?:https?:|mailto:|tel:|\/|#|\.\.?\/)/iu.test(compact)) return true;
  return !compact.includes(":");
}

function renderInline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/gu, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/gu, "<strong>$1</strong>")
    .replace(/__([^_]+)__/gu, "<strong>$1</strong>")
    .replace(/\[(.+?)\]\(([^)]+)\)/gu, (source, label: string, href: string) =>
      safeLink(href) ? `<a href="${href}">${label}</a>` : source,
    )
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/gu, "<em>$1</em>");
}

/**
 * Render the portable Markdown subset used by namespace helpers.
 *
 * The implementation is dependency-free for Workers and covers headings,
 * unordered lists, paragraphs, hard line breaks, emphasis, code, and links.
 * Markdown text and attributes are escaped, and links allow only safe protocols.
 * Use HTML explicitly for trusted raw markup.
 */
export function markdownToHtml(value: string): string {
  const blocks = value
    .replaceAll("\r\n", "\n")
    .trim()
    .split(/\n{2,}/u);
  if (blocks.length === 1 && blocks[0] === "") return "";
  return blocks
    .map((block) => {
      const heading = block.match(/^(#{1,6})\s+(.+)$/u);
      if (heading !== null) {
        const level = heading[1]?.length ?? 1;
        return `<h${level}>${renderInline(heading[2] ?? "")}</h${level}>`;
      }
      const lines = block.split("\n");
      if (lines.every((line) => /^\s*[-*+]\s+/u.test(line))) {
        const items = lines
          .map((line) => line.replace(/^\s*[-*+]\s+/u, ""))
          .map((line) => `<li>${renderInline(line)}</li>`)
          .join("\n");
        return `<ul>\n${items}\n</ul>`;
      }
      return `<p>${lines.map(renderInline).join("<br />\n")}</p>`;
    })
    .join("\n");
}

/** Convert rich text to the HTML string sent to an Odoo HTML field. */
export function richTextToHtml(
  value: RichText,
  markdownByDefault = true,
): string {
  if (value instanceof HTML) return value.value;
  if (value instanceof Markdown || markdownByDefault) {
    return markdownToHtml(String(value));
  }
  return `<p>${escapeHtml(String(value))}</p>`;
}

/** Process explicit content wrappers in an Odoo values object. */
export function processContentValues(
  values: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => {
      if (value instanceof HTML) return [key, value.value];
      if (value instanceof Markdown) return [key, markdownToHtml(value.value)];
      return [key, value];
    }),
  );
}
