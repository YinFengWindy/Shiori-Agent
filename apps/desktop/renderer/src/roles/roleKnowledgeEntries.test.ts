import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { knowledgeEntryHasContent, knowledgeEntryLabel } from "./roleKnowledgeEntries";

describe("knowledgeEntryHasContent", () => {
  it("treats a freshly added entry as empty", () => {
    assert.equal(knowledgeEntryHasContent({ id: "a", content: "", primary_keys: [], secondary_keys: [] }), false);
    assert.equal(knowledgeEntryHasContent({ title: "   ", content: "\n" }), false);
  });

  it("counts a title, content, or any keyword as written content", () => {
    assert.equal(knowledgeEntryHasContent({ title: "雨天" }), true);
    assert.equal(knowledgeEntryHasContent({ content: "她喜欢听雨。" }), true);
    assert.equal(knowledgeEntryHasContent({ primary_keys: ["雨"] }), true);
    assert.equal(knowledgeEntryHasContent({ keywords: ["legacy"] }), true);
    assert.equal(knowledgeEntryHasContent({ secondary_keys: ["伞"] }), true);
  });
});

describe("knowledgeEntryLabel", () => {
  it("falls back to the 1-based position for untitled entries", () => {
    assert.equal(knowledgeEntryLabel({ title: "雨天" }, 0), "雨天");
    assert.equal(knowledgeEntryLabel({ title: " " }, 2), "条目 3");
  });
});
