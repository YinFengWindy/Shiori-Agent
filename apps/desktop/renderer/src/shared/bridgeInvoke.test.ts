import assert from "node:assert/strict";
import { test } from "node:test";
import { BridgeError } from "@yinfengwindy/shiori-sdk";
import { invokeBridgePayload } from "./bridgeInvoke";

test("failed RPC envelopes retain the stable code and independent diagnostic detail", async () => {
  await assert.rejects(invokeBridgePayload(async ({ method }) => ({ id: "1", type: "response", method, payload: {}, error: {
    code: "internal_error", message: "本地服务处理失败", details: { detail: "OSError: config read denied" },
  } }), "runtime.status", {}), (failure) => {
    assert.ok(failure instanceof BridgeError);
    assert.equal(failure.code, "internal_error");
    assert.equal(failure.message, "本地服务处理失败");
    assert.equal(failure.details?.detail, "OSError: config read denied");
    return true;
  });
});
