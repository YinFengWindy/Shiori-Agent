import assert from "node:assert/strict";
import { test } from "node:test";
import { getChatDraft, getChatDraftKey, subscribeChatDrafts, submitChatDraft, updateChatDraft } from "./chatDraftStore";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

test("draft snapshots stay stable and session updates never touch the empty identity", () => {
  const a = getChatDraftKey("snapshots-a")!;
  const b = getChatDraftKey("snapshots-b")!;
  const empty = getChatDraft(null);
  assert.equal(getChatDraftKey(""), null);
  assert.equal(getChatDraft(a), getChatDraft(a));
  let updates = 0;
  const unsubscribe = subscribeChatDrafts(() => { updates += 1; });
  updateChatDraft(null, (draft) => ({ ...draft, content: "unowned" }));
  updateChatDraft(a, (draft) => ({ ...draft, content: "A" }));
  const snapshot = getChatDraft(a);
  updateChatDraft(a, (draft) => draft);
  assert.equal(updates, 1);
  assert.equal(getChatDraft(a), snapshot);
  assert.equal(getChatDraft(b), empty);
  assert.equal(getChatDraft(null), empty);
  unsubscribe();
  updateChatDraft(b, (draft) => ({ ...draft, content: "B" }));
  assert.equal(updates, 1);
  assert.equal(getChatDraft(a).content, "A");
});

test("failed sends restore the complete source snapshot, including quotes, independently of subscriptions", async () => {
  const key = "role:restore";
  const request = { content: "正文", attachments: ["/image.png"], replyTarget: {
    messageId: "source", content: "引用", preview: "引用", sender: "Mira",
  } };
  updateChatDraft(key, () => request);
  const result = deferred<boolean>();
  const sending = submitChatDraft(key, async (sent) => { assert.equal(sent, request); return result.promise; });
  assert.deepEqual(getChatDraft(key), { content: "", attachments: [], replyTarget: null });
  updateChatDraft("role:elsewhere", (draft) => ({ ...draft, content: "另一会话" }));
  result.resolve(false);
  assert.equal(await sending, false);
  assert.equal(getChatDraft(key), request);
  assert.equal(getChatDraft("role:elsewhere").content, "另一会话");
});

test("late send success or failure preserves edits made after submitting, even if text was erased", async () => {
  for (const outcome of [true, false]) {
    const key = `role:edited-${outcome}`;
    updateChatDraft(key, (draft) => ({ ...draft, content: "old" }));
    const result = deferred<boolean>();
    const sending = submitChatDraft(key, () => result.promise);
    updateChatDraft(key, (draft) => ({ ...draft, content: "new" }));
    updateChatDraft(key, (draft) => ({ ...draft, content: "" }));
    const edited = getChatDraft(key);
    result.resolve(outcome);
    await sending;
    assert.equal(getChatDraft(key), edited);
  }
});

test("a rejected send restores its snapshot and propagates the error to the UI boundary", async () => {
  const key = "role:rejection";
  updateChatDraft(key, (draft) => ({ ...draft, content: "retry me" }));
  await assert.rejects(submitChatDraft(key, async () => { throw new Error("offline"); }), /offline/);
  assert.equal(getChatDraft(key).content, "retry me");
  let sends = 0;
  assert.equal(await submitChatDraft(null, async () => { sends += 1; return true; }), false);
  assert.equal(await submitChatDraft("role:empty", async () => { sends += 1; return true; }), false);
  assert.equal(sends, 0);
});
