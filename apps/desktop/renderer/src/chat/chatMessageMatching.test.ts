import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createChatMessageMatcher, getChatMessageMatchStrength } from "./chatMessageMatching";
import type { SessionMessage } from "../shared/types";

describe("getChatMessageMatchStrength", () => {
  it("rejects conflicting durable identities even for the same assistant turn or render key", () => {
    const current: SessionMessage = { id: "a1", seq: 1, render_id: "local:a", role: "assistant", content: "same", metadata: { client_message_id: "turn" } };
    assert.equal(getChatMessageMatchStrength(current, { ...current, id: "a2", seq: 2 }), 0);
    assert.equal(getChatMessageMatchStrength(current, { ...current, id: undefined, seq: 2 }), 0);
  });

  it("does not merge repeated local errors or user turns with distinct render identities", () => {
    for (const role of ["error", "user"]) {
      const current = { role, content: "same", render_id: "local:1" };
      assert.equal(getChatMessageMatchStrength(current, { ...current, render_id: "local:2" }), 0);
      assert.equal(getChatMessageMatchStrength(current, { ...current }), 3);
    }
  });

  it("rejects empty prefixes, unrelated proactive replies, and user text extensions", () => {
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "", streaming: true }, { id: "a", role: "assistant", content: "reply" }), 0);
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "partial", streaming: true }, { id: "a", role: "assistant", content: "unrelated" }), 0);
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "hello", streaming: true }, { id: "a", role: "assistant", content: "hello again", metadata: { proactive: true } }), 0);
    assert.equal(getChatMessageMatchStrength({ role: "user", content: "hello" }, { id: "u", role: "user", content: "hello again" }), 0);
  });

  it("does not treat an empty persisted reasoning_content as conflicting with local thinking (#300)", () => {
    const current = { role: "assistant", content: "你好", reasoning_content: "让我想想怎么回复" };
    // Persisted row omits reasoning_content entirely (proactive/interrupted/no-reasoning
    // provider) and content is a continuation: this must still be treated as the same row.
    assert.equal(getChatMessageMatchStrength(current, { id: "a", role: "assistant", content: "你好，最近如何" }), 1);
    // Persisted row explicitly has an empty reasoning_content string: same as above.
    assert.equal(getChatMessageMatchStrength(current, { id: "a", role: "assistant", content: "你好，最近如何", reasoning_content: "" }), 1);
    // Persisted row has non-empty reasoning_content that conflicts with local thinking:
    // this remains a genuine identity conflict and must not be merged.
    assert.equal(getChatMessageMatchStrength(current, { id: "a", role: "assistant", content: "你好，最近如何", reasoning_content: "完全不同的思考" }), 0);
  });

  it("preserves Thinking-first and tool-only streaming transitions with positive evidence", () => {
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "", reasoning_content: "think" }, { id: "a", role: "assistant", content: "reply", reasoning_content: "thinking" }), 1);
    const tool_chain = [{ text: "", reasoning_content: "", calls: [{ call_id: "call-1", name: "lookup", status: "success", arguments: {}, final_arguments: {}, result: "done" }] }];
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "", tool_chain }, { id: "a", role: "assistant", content: "reply", tool_chain }), 2);
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "", tool_chain }, { id: "a", role: "assistant", content: "reply", tool_chain, media: ["image.png"] }), 2);
    const anonymousTools = tool_chain.map((group) => ({ ...group, calls: group.calls.map((call) => ({ ...call, call_id: "" })) }));
    assert.equal(getChatMessageMatchStrength({ role: "assistant", content: "", tool_chain: anonymousTools }, { id: "a", role: "assistant", content: "reply", tool_chain: anonymousTools }), 0);
  });
});

describe("createChatMessageMatcher", () => {
  it("bounds content acknowledgement by neighbors while allowing a reply-before-user acknowledgement", () => {
    const find = createChatMessageMatcher([
      { id: "old", seq: 5, role: "assistant", content: "old" },
      { role: "user", content: "same" },
      { id: "reply", seq: 7, role: "assistant", content: "reply" },
    ]);
    assert.equal(find({ id: "history", seq: 2, role: "user", content: "same" }), -1);
    assert.equal(find({ id: "new-user", seq: 6, role: "user", content: "same" }), 1);
  });
});
