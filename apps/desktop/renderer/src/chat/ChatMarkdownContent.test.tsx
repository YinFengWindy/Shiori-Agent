/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatMarkdownContent, safeMarkdownUrl } from "./ChatMarkdownContent";

describe("ChatMarkdownContent", () => {
  it("renders common Markdown structures with GFM support", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content={"# Heading\n\n**bold** and *italic*\n\n- first\n- second\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n" + "\x60\x60\x60ts\nconst answer = 42;\n\x60\x60\x60"} />,
    );

    assert.match(markup, /<h1[^>]*>Heading<\/h1>/);
    assert.match(markup, /<strong>bold<\/strong>/);
    assert.match(markup, /<em>italic<\/em>/);
    assert.match(markup, /<ul[^>]*>/);
    assert.match(markup, /<table>/);
    assert.match(markup, /<code class="language-ts">const answer = 42;\n<\/code>/);
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
    assert.equal(safeMarkdownUrl("data:text/plain,hello"), null);
  });

  it("keeps authorized links as links and normalizes supported URLs", () => {
    const markup = renderToStaticMarkup(
      <ChatMarkdownContent content="[docs](https://example.com/docs) [mail](mailto:hello@example.com)" />,
    );

    assert.match(markup, /href="https:\/\/example\.com\/docs"/);
    assert.match(markup, /href="mailto:hello@example\.com"/);
    assert.equal(safeMarkdownUrl("javascript:alert(1)"), null);
  });
});
