import assert from "node:assert/strict";
import { test } from "node:test";
import { readLiveCancel, readLiveReply, readLiveReplyIds } from "./contract";

test("a live reply needs the live source and every identity field", () => {
  assert.deepEqual(
    readLiveReply({ source: "live", role_id: "mira", reply_id: "r1", run_id: "run", text: " 你好 " }),
    { roleId: "mira", replyId: "r1", runId: "run", text: "你好" },
  );
  assert.throws(() => readLiveReply({ source: "chat", role_id: "mira", reply_id: "r1", run_id: "run", text: "x" }), /来源/);
  assert.throws(() => readLiveReply({ source: "live", role_id: "mira", run_id: "run", text: "x" }), /reply_id/);
});

test("a malformed reply still yields its ids when both are present", () => {
  assert.deepEqual(readLiveReplyIds({ reply_id: "r1", run_id: "run", text: 3 }), { reply_id: "r1", run_id: "run" });
  assert.equal(readLiveReplyIds({ reply_id: "r1" }), null);
});

test("a cancel without run_id targets every live run", () => {
  assert.deepEqual(readLiveCancel({}), {});
  assert.deepEqual(readLiveCancel({ run_id: "run" }), { runId: "run" });
  assert.throws(() => readLiveCancel({ run_id: 3 }), /run_id/);
});
