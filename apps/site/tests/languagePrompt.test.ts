import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { languagePromptMemory, shouldOfferEnglish } from "../src/lib/languagePrompt";

describe("languagePromptMemory", () => {
  it("reads nothing stored as unanswered, and any stored value as an answer", () => {
    assert.equal(languagePromptMemory(null), "unanswered");
    assert.equal(languagePromptMemory("dismissed"), "answered");
    assert.equal(languagePromptMemory("switched"), "answered");
    assert.equal(languagePromptMemory(""), "answered");
  });
});

describe("shouldOfferEnglish", () => {
  it("offers the English site to a browser that names no Chinese", () => {
    assert.equal(shouldOfferEnglish(["en-US", "en"], "unanswered"), true);
    assert.equal(shouldOfferEnglish(["ja-JP", "fr"], "unanswered"), true);
  });

  it("stays quiet when any of the browser's languages is Chinese, in any form", () => {
    assert.equal(shouldOfferEnglish(["zh-CN"], "unanswered"), false);
    assert.equal(shouldOfferEnglish(["en-US", "zh"], "unanswered"), false);
    assert.equal(shouldOfferEnglish(["en", "zh-Hant-TW"], "unanswered"), false);
    assert.equal(shouldOfferEnglish(["ZH-tw"], "unanswered"), false);
  });

  it("does not take a language merely starting with the letters zh for Chinese", () => {
    // `zha` (Zhuang) is not Chinese.
    assert.equal(shouldOfferEnglish(["zha"], "unanswered"), true);
  });

  it("asks once: a remembered answer, or storage it cannot read, keeps it away", () => {
    assert.equal(shouldOfferEnglish(["en-US"], "answered"), false);
    assert.equal(shouldOfferEnglish(["en-US"], "unreadable"), false);
  });

  it("stays quiet when the browser names no language at all", () => {
    assert.equal(shouldOfferEnglish([], "unanswered"), false);
  });
});
