import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeError, errorFeedback, errorFeedbackText, errorMessage } from "./errors";

test("structured bridge causes stay separate and credentials are scrubbed in both fields", () => {
  const view = errorFeedback(new BridgeError("本地服务处理失败", "internal_error", { detail: 'OSError: https://host/?key=secret-value&model=keep&key=another-secret {"api_key":"json-secret"} Bearer header-secret' }));
  assert.match(view.detail, /model=keep/);
  assert.equal(view.message, "本地服务处理失败");
  assert.match(view.detail, /OSError/);
  assert.doesNotMatch(view.detail, /secret-value|json-secret|header-secret|another-secret/);
  assert.equal(errorMessage(new BridgeError("请填写角色名称", "invalid_request")), "请填写角色名称");
});

test("legacy string state keeps the summary and cause recoverable without exception prefixes", () => {
  const view = errorFeedback(errorFeedbackText(new BridgeError("请求超时", "bridge_timeout", { detail: "request timed out after 30ms" })));
  assert.equal(view.message, "请求超时");
  assert.match(view.detail, /request timed out/);
  assert.equal(errorFeedback(null).message, "操作未完成，请重试");
  assert.equal(errorFeedback(null).detail, "");
  assert.equal(errorMessage(new Error("Error invoking remote method 'desktop:test': Error: 录音回放失败")), "录音回放失败");
});
