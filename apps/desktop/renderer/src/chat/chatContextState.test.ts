import assert from "node:assert/strict";
import { test } from "node:test";
import { contextResultFeedback, contextResultLabel, contextUsageLabel, mergeContextStatus, type ChatContextStatus } from "./chatContextState";

const status: ChatContextStatus = {
  session_key: "role:mira", context_key: "user", model: "model", model_identity: "identity",
  tokens: 32000, source: "actual", model_context_window: 128000, input_limit_tokens: 100000,
  can_compact: true, busy: false, reason: "", result: null,
};

test("usage divides by total model capacity and preserves unknown values", () => {
  assert.equal(contextUsageLabel(status).ratio, .25);
  assert.match(contextUsageLabel(status).label, /25%（实际）/);
  assert.match(contextUsageLabel({ ...status, source: "anchor_delta" }).label, /锚点估算/);
  for (const value of [null, { ...status, tokens: null }, { ...status, model_context_window: 0 }]) {
    assert.deepEqual(contextUsageLabel(value), { label: "上下文用量未知", ratio: null });
  }
});

test("failure reports committed memory without claiming the window was changed", () => {
  const failure = { ...status, result: { committed: false, memory_committed: true, before_tokens: 32000, after_tokens: null, retained_turns: 2, failure_stage: "summary", error: "summary offline" } };
  assert.equal(contextResultLabel(failure), "记忆已整理、压缩失败：压缩未完成，请稍后重试");
  assert.equal(contextResultFeedback(failure).detail, "summary offline");
});

test("JSON parser diagnostics remain in feedback details and keep the readable stage summary", () => {
  const result = contextResultFeedback({ ...status, result: { committed: false, memory_committed: true, before_tokens: 32000, after_tokens: null, retained_turns: 2, failure_stage: "summary", error: "工作摘要生成失败，请稍后重试", detail: "JSONDecodeError: Expecting value: line 1 column 1 (char 0) token=private-value" } });
  assert.equal(result.message, "记忆已整理、压缩失败：工作摘要生成失败，请稍后重试");
  assert.match(result.detail, /Expecting value/);
  assert.doesNotMatch(result.detail, /private-value/);
});

test("a busy read keeps only the last usage numbers of the same session", () => {
  const previous = { ...status, result: { committed: true, memory_committed: true, before_tokens: 1, after_tokens: 2, retained_turns: 2, failure_stage: "", error: "" } };
  const busy = { ...status, tokens: null, source: null, model_context_window: null, input_limit_tokens: null, busy: true, can_compact: false, reason: "正在回复" };
  assert.deepEqual(mergeContextStatus(previous, busy), { ...busy, tokens: 32000, source: "actual", model_context_window: 128000, input_limit_tokens: 100000 });
  const other = { ...busy, session_key: "role:other" };
  assert.equal(mergeContextStatus(previous, other), other);
});
