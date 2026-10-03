import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeError } from "@yinfengwindy/shiori-sdk";
import { describeStoryFailure } from "./storyFailure";

test("Story diagnostics never replace the operation summary and remain scrubbed", () => {
  const result = describeStoryFailure(new BridgeError("本地服务处理失败", "internal_error", { detail: "ValueError: Story revision internal token=private-value" }), "剧情列表加载失败");
  assert.equal(result.error, "剧情列表加载失败");
  assert.match(result.errorDetail ?? "", /Story revision internal/);
  assert.doesNotMatch(result.errorDetail ?? "", /private-value/);
  assert.equal(describeStoryFailure(new Error("database missing")).error, "剧情操作未完成，请重试");
});

test("Story-owned validation and recovery instructions stay in the summary", () => {
  const result = describeStoryFailure(new BridgeError("剧情已更新，请重新加载后再试", "revision_conflict"));
  assert.equal(result.error, "剧情已更新，请重新加载后再试");
  assert.equal(result.errorDetail, undefined);
});
