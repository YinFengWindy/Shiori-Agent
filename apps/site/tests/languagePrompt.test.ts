import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { shouldOfferEnglish } from "../src/lib/languagePrompt";

describe("shouldOfferEnglish", () => {
  it("offers the English site to a browser that names no Chinese", () => {
    assert.equal(shouldOfferEnglish(["en-US", "en"], null), true);
    assert.equal(shouldOfferEnglish(["ja-JP", "fr"], null), true);
  });

  it("stays quiet when any of the browser's languages is Chinese, in any form", () => {
    assert.equal(shouldOfferEnglish(["zh-CN"], null), false);
    assert.equal(shouldOfferEnglish(["en-US", "zh"], null), false);
    assert.equal(shouldOfferEnglish(["en", "zh-Hant-TW"], null), false);
    assert.equal(shouldOfferEnglish(["ZH-tw"], null), false);
  });

  it("does not take a language merely starting with the letters zh for Chinese", () => {
    // `zha` (Zhuang) is not Chinese.
    assert.equal(shouldOfferEnglish(["zha"], null), true);
  });

  it("asks once: any remembered answer, or an unreadable store, keeps it away", () => {
    assert.equal(shouldOfferEnglish(["en-US"], "dismissed"), false);
    assert.equal(shouldOfferEnglish(["en-US"], "switched"), false);
    assert.equal(shouldOfferEnglish(["en-US"], ""), false);
  });

  it("stays quiet when the browser names no language at all", () => {
    assert.equal(shouldOfferEnglish([], null), false);
  });
});
