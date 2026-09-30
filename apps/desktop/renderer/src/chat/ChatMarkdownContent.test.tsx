/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { normalizeExternalLink } from "../../../src/externalLinks";
import { ChatMarkdownContent } from "./ChatMarkdownContent";

describe("ChatMarkdownContent", () => {
  it("renders common Markdown structures with GFM support", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content={"# Heading\n\n**bold** and *italic*\n\n- first\n- second\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n" + "\x60\x60\x60ts\nconst answer = 42;\n\x60\x60\x60"} />,
    );

    assert.match(markup, /<h1[^>]*>Heading<\/h1>/);
    assert.match(markup, /<strong>bold<\/strong>/);
    assert.match(markup, /<em>italic<\/em>/);
    assert.match(markup, /<ul[^>]*>/);
    assert.match(markup, /<table[^>]*>/);
    assert.match(markup, /data-testid="chat-code-block"/);
    assert.match(markup, />ts<\/span>/);
    assert.match(markup, /<code>const answer = 42;<\/code>/);
  });

  it("closes bold next to CJK punctuation", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content={"她说**“你好”**然后走了\n\n这是**重点：**后面\n\n**加粗（括号）**后文"} />,
    );

    assert.match(markup, /<strong>“你好”<\/strong>然后走了/);
    assert.match(markup, /<strong>重点：<\/strong>后面/);
    assert.match(markup, /<strong>加粗（括号）<\/strong>后文/);
    assert.doesNotMatch(markup, /\*\*/);
  });

  it("keeps single newlines as line breaks and styles minor headings", () => {
    const markup = renderToStaticMarkup(<ChatMarkdownContent content={"第一行\n第二行\n\n#### 四级标题"} />);

    assert.match(markup, /第一行<br\/>\s*第二行/);
    assert.match(markup, /<h4 class="[^"]*font-semibold[^"]*">四级标题<\/h4>/);
  });

  it("does not render raw HTML or unsafe links", () => {
    const rawHtmlMarkup = renderToStaticMarkup(
      <ChatMarkdownContent content="<span>hidden markup</span> visible text" />,
    );
    const unsafeLinkMarkup = renderToStaticMarkup(
      <ChatMarkdownContent content="[run](javascript:alert(1))" />,
    );

    assert.doesNotMatch(rawHtmlMarkup, /<span/);
    assert.match(rawHtmlMarkup, /visible text/);
    assert.doesNotMatch(unsafeLinkMarkup, /href=/);
    assert.match(unsafeLinkMarkup, /run/);
    assert.equal(normalizeExternalLink("data:text/plain,hello"), null);
  });

  it("does not load remote Markdown images", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content="![remote image](https://example.com/image.png)" />,
    );

    assert.doesNotMatch(markup, /<img/);
    assert.match(markup, /remote image/);
  });

  it("keeps authorized links as links and normalizes supported URLs", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content="[docs](https://example.com/docs) [mail](mailto:hello@example.com)" />,
    );

    assert.match(markup, /href="https:\/\/example\.com\/docs"/);
    assert.match(markup, /href="mailto:hello@example\.com"/);
    assert.equal(normalizeExternalLink("javascript:alert(1)"), null);
  });

  it("labels a fence without a language and keeps its text escaped", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content={"\x60\x60\x60\n<script>alert(1)</script>\n\x60\x60\x60"} />,
    );

    assert.match(markup, />代码<\/span>/);
    assert.match(markup, /&lt;script&gt;/);
    assert.doesNotMatch(markup, /<script>/);
  });

  it("wraps tables in a bordered scroll container", () => {
    const markup = renderToStaticMarkup(<ChatMarkdownContent content={"| A | B |\n| --- | --- |\n| 1 | 2 |"} />);

    assert.match(markup, /class="chat-markdown-table[^"]*overflow-x-auto/);
    assert.match(markup, /<th[^>]*>A<\/th>/);
  });
});
