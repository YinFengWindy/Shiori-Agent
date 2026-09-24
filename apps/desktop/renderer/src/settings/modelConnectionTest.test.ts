import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BridgeResponse, ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelConnectionKey, selectModelConnectionTestView, testModelConnection } from "./modelConnectionTest";

const registration: ModelRegistrationFormData = { id: "r", provider: "deepseek", baseUrl: "https://api.deepseek.com", apiKey: "key", model: "deepseek-chat", effort: "none" };

function respond(payload: Record<string, unknown>, error: BridgeResponse["error"] = null) {
  const requests: unknown[] = [];
  const invoke = async (request: { method: string; payload: Record<string, unknown> }) => {
    requests.push(request);
    return { id: "1", type: "response", method: request.method, payload, error } as BridgeResponse;
  };
  return { invoke, requests };
}

describe("model connection test", () => {
  it("sends the unsaved draft in bridge field names", async () => {
    const { invoke, requests } = respond({ ok: true, latency_ms: 42 });
    assert.deepEqual(await testModelConnection(invoke, registration), { status: "success", latencyMs: 42 });
    assert.deepEqual(requests, [{ method: "models.test", payload: { provider: "deepseek", model: "deepseek-chat", base_url: "https://api.deepseek.com", api_key: "key" } }]);
  });

  it("reports an endpoint rejection as a failure view", async () => {
    const { invoke } = respond({ ok: false, message: "AuthenticationError: 401" });
    assert.deepEqual(await testModelConnection(invoke, registration), { status: "failure", message: "AuthenticationError: 401" });
  });

  it("raises bridge errors such as incomplete fields", async () => {
    const { invoke } = respond({}, { code: "invalid_request", message: "请先填写有效的API Key" });
    await assert.rejects(testModelConnection(invoke, registration), /API Key/);
  });

  it("keeps a result only while the connection fields are unchanged", () => {
    const record = { key: modelConnectionKey(registration), view: { status: "success" as const, latencyMs: 1 } };
    assert.equal(selectModelConnectionTestView(record, { ...registration, effort: "max" }).status, "success");
    assert.equal(selectModelConnectionTestView(record, { ...registration, apiKey: "other" }).status, "idle");
    assert.equal(selectModelConnectionTestView(null, registration).status, "idle");
  });
});
