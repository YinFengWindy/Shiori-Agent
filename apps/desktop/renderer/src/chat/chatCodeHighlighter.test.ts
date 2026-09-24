/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { highlightChatCode } from "./chatCodeHighlighter";
import { getChatCodeLanguage } from "./chatCodeHighlight";

describe("highlightChatCode", () => {
  it("highlights registered languages and their aliases", () => {
    assert.match(highlightChatCode("const a = 1;", "ts") ?? "", /<span class="hljs-keyword">const<\/span>/);
    assert.match(highlightChatCode("print('hi')", "py") ?? "", /hljs-/);
  });

  it("escapes the code text", () => {
    const html = highlightChatCode("<img src=x onerror=alert(1)>", "html") ?? "";
    assert.doesNotMatch(html, /<img/);
    assert.match(html, /&lt;/);
  });

  it("returns null for unknown or missing languages", () => {
    assert.equal(highlightChatCode("x", "brainfuck"), null);
    assert.equal(highlightChatCode("x", ""), null);
  });
});

describe("getChatCodeLanguage", () => {
  it("reads the language from the markdown class", () => {
    assert.equal(getChatCodeLanguage("language-TypeScript"), "typescript");
    assert.equal(getChatCodeLanguage("language-c++"), "c++");
    assert.equal(getChatCodeLanguage(undefined), "");
  });
});
