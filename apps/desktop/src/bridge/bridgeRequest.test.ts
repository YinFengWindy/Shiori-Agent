import assert from "node:assert/strict";
import test from "node:test";
import type { BridgeResponse } from "./shared.js";
import { invokeBridgeOrThrow } from "./bridgeRequest.js";

function bridgeAnswering(error: BridgeResponse["error"]) {
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  return {
    requests,
    invoke: async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "r", type: "response", method: request.method, payload: { ok: true }, error };
    },
  };
}

test("returns the response payload when the backend accepts the request", async () => {
  const bridge = bridgeAnswering(null);
  const payload = await invokeBridgeOrThrow(bridge, { method: "demo.run", payload: { value: 1 } });
  assert.deepEqual(payload, { ok: true });
  assert.deepEqual(bridge.requests, [{ method: "demo.run", payload: { value: 1 } }]);
});

test("rejects with the backend error message", async () => {
  const bridge = bridgeAnswering({ code: "invalid_request", message: "boom" });
  await assert.rejects(invokeBridgeOrThrow(bridge, { method: "demo.run", payload: {} }), { message: "boom" });
});
