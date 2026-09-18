import { describe, expect, it } from "vitest";

import { decodeBase64, encodeBase64 } from "../src/binary.js";
import { Cmd } from "../src/commands.js";
import {
  HTML,
  Markdown,
  markdownToHtml,
  richTextToHtml,
} from "../src/content.js";

describe("portable Odoo helpers", () => {
  it("builds every x2many command", () => {
    expect(Cmd.create({ name: "A" })).toEqual([0, 0, { name: "A" }]);
    expect(Cmd.update(3, { name: "B" })).toEqual([1, 3, { name: "B" }]);
    expect(Cmd.delete(3)).toEqual([2, 3, 0]);
    expect(Cmd.unlink(3)).toEqual([3, 3, 0]);
    expect(Cmd.link(3)).toEqual([4, 3, 0]);
    expect(Cmd.clear()).toEqual([5, 0, 0]);
    expect(Cmd.set([2, 3])).toEqual([6, 0, [2, 3]]);
  });

  it("renders dependency-free Markdown and preserves explicit HTML", () => {
    expect(markdownToHtml("# Title\n\n- one\n- **two**")).toBe(
      "<h1>Title</h1>\n<ul>\n<li>one</li>\n<li><strong>two</strong></li>\n</ul>",
    );
    expect(richTextToHtml(new Markdown("`code`"))).toBe(
      "<p><code>code</code></p>",
    );
    expect(richTextToHtml(new HTML("<b>ready</b>"))).toBe("<b>ready</b>");
  });

  it("escapes Markdown HTML and rejects unsafe link protocols", () => {
    expect(markdownToHtml('<img src=x onerror="alert(1)">')).toBe(
      "<p>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</p>",
    );
    expect(markdownToHtml("[click](javascript:alert(1))")).toBe(
      "<p>[click](javascript:alert(1))</p>",
    );
    expect(markdownToHtml("[click](java\tscript:alert(1))")).toBe(
      "<p>[click](java\tscript:alert(1))</p>",
    );
    expect(markdownToHtml('[safe](https://example.com/?q="x")')).toBe(
      '<p><a href="https://example.com/?q=&quot;x&quot;">safe</a></p>',
    );
    expect(richTextToHtml("<b>plain</b>", false)).toBe(
      "<p>&lt;b&gt;plain&lt;/b&gt;</p>",
    );
    expect(richTextToHtml(new HTML("<b>trusted</b>"), false)).toBe(
      "<b>trusted</b>",
    );
  });

  it("round-trips base64 without Node Buffer", () => {
    const bytes = new Uint8Array([0, 1, 127, 128, 255]);
    expect(decodeBase64(encodeBase64(bytes))).toEqual(bytes);
  });
});
