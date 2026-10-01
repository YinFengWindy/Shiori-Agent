import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { BridgeError } from "@shiori/sdk";
import { mountTestComponent } from "@shiori/sdk/testing";
import { useStoryPresentationOperation } from "./useStoryPresentationOperation";

test("Story commands store a safe summary and separate diagnostic detail", async () => {
  let operation!: ReturnType<typeof useStoryPresentationOperation>;
  function Probe() { operation = useStoryPresentationOperation(); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => operation.run(async () => { throw new BridgeError("本地服务处理失败", "internal_error", { detail: "provider response invalid token=private-value" }); }, () => assert.fail("failed command cannot apply")));
    assert.equal(operation.error, "剧情操作未完成，请重试");
    assert.match(operation.errorDetail ?? "", /provider response invalid/);
    assert.doesNotMatch(operation.errorDetail ?? "", /private-value/);
    assert.equal(operation.busy, false);
    await act(async () => operation.clearError());
    assert.equal(operation.error, "");
    assert.equal(operation.errorDetail, undefined);
  } finally { await view.cleanup(); }
});
