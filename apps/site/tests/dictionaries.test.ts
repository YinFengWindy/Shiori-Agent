import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { SHOWCASE_CLIP_IDS } from "../src/content/showcase";
import { DICTIONARIES, pageTitle, siteText } from "../src/i18n";
import { LOCALES } from "../src/i18n/locales";
import { DOWNLOAD_ANCHOR_ID } from "../src/lib/siteMeta";

/*
 * The dictionaries' type makes the English one give every key of the
 * Chinese one (i18n/zh.ts `SiteDictionary`); this checks the same at run
 * time, where a widened type or a stray cast could let a key slip.
 */

/** Every leaf of a dictionary: its key path and its value. */
function leaves(value: unknown, path = ""): [string, unknown][] {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.entries(value).flatMap(([key, child]) => leaves(child, path ? `${path}.${key}` : key));
  }
  return [[path, value]];
}

describe("site dictionaries (#806)", () => {
  const zhLeaves = leaves(DICTIONARIES.zh);

  it("give every language the same keys", () => {
    const keys = zhLeaves.map(([key]) => key).sort();
    assert.ok(keys.length > 40, "the Chinese dictionary is unexpectedly small");
    for (const locale of LOCALES) assert.deepEqual(leaves(DICTIONARIES[locale]).map(([key]) => key).sort(), keys, `${locale} keys`);
  });

  it("fill every key with words: a non-empty string, and English words in the English dictionary", () => {
    for (const locale of LOCALES) {
      for (const [key, value] of leaves(DICTIONARIES[locale])) {
        assert.ok(typeof value === "string" && value.trim() !== "", `${locale}.${key} is empty or not text`);
      }
    }
    // Chinese only where the switch names Chinese itself.
    const chinese = /\p{Script=Han}/u;
    for (const [key, value] of leaves(DICTIONARIES.en)) {
      if (key === "languageSwitch.text" || key === "languageSwitch.label") continue;
      assert.doesNotMatch(String(value), chinese, `en.${key} still has Chinese: ${String(value)}`);
    }
  });

  it("speak a line for every narrative line and words for every showcase block", () => {
    for (const locale of LOCALES) {
      const text = siteText(locale);
      assert.deepEqual(Object.keys(text.narrative.lines), NARRATIVE_LINES.map((line) => line.id), `${locale} narrative lines`);
      assert.deepEqual(Object.keys(text.showcase.features), [...SHOWCASE_CLIP_IDS], `${locale} showcase blocks`);
    }
  });

  it("keeps the narrative's anchors distinct and clear of the home page's other anchors", () => {
    const ids = NARRATIVE_LINES.map((line) => line.id);
    assert.equal(new Set(ids).size, ids.length);
    for (const other of [...SHOWCASE_CLIP_IDS, DOWNLOAD_ANCHOR_ID, "site-loader"]) assert.ok(!ids.includes(other as never), `${other} is taken`);
    for (const id of ids) assert.match(id, /^[a-z][a-z0-9-]*$/, `${id} is not a plain anchor`);
  });

  it("titles a page by its name and the site's, in the page's language", () => {
    assert.equal(pageTitle("更新日志", "zh"), "更新日志 · Shiori AI 伴侣");
    assert.equal(pageTitle("Changelog", "en"), "Changelog · Shiori AI Companion");
  });
});
