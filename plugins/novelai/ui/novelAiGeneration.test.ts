import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { BridgeError, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import { loadHistory, refreshReadiness, submitGenerate } from "./novelAiGeneration";
import { getNovelAiState, resetNovelAiPageStoreForTests } from "./novelAiPageStore";

function client(handler: (method: string) => unknown): PluginRpcClient {
  return createFakePluginClient({ call: async <T,>(method: string) => handler(method) as T });
}

const result = {
  record_id: "rec-1", created_at: "", mode: "txt2img", model: "m", seed: 1, width: 1024, height: 1024, output_paths: ["D:/out/1.png"],
  request_path: "", meta_path: "", wrote_back_to_role: false, role_asset_paths: [],
};
const historyRecord = {
  id: "rec-1", created_at: "", role_id: "rin", session_key: "", mode: "txt2img", prompt: "", negative_prompt: "", model: "m", sampler: "",
  steps: 0, seed: 1, width: 1024, height: 1024, base_image_path: "", output_paths: ["D:/out/1.png"], wrote_back_to_role: false, role_asset_paths: [],
};

/** The host services whose `feedback` the functions under test report to. */
let fake = createFakeHostServices();

afterEach(() => {
  resetNovelAiPageStoreForTests();
  fake = createFakeHostServices();
});

describe("submitGenerate", () => {
  it("flips submitting synchronously, then publishes the result as the revealed, selected record", async () => {
    const rpc = client((method) => (method === "generate" ? { result } : { records: [historyRecord] }));
    const pending = submitGenerate(rpc, fake.host.feedback, { role_id: "rin", prompt: "cat" });
    assert.equal(getNovelAiState().submitting, true);
    assert.equal(await pending, null);
    const state = getNovelAiState();
    assert.equal(state.submitting, false);
    assert.equal(state.revealRecordId, "rec-1");
    assert.equal(state.selectedRecordId, "rec-1");
    assert.equal(state.history.length, 1);
    assert.equal(state.failure, null);
  });

  it("keeps a classified failure for the canvas and returns it for the toast", async () => {
    const rpc = client(() => { throw new BridgeError("NovelAI 拒绝了当前 token（HTTP 401）", "novelai_unauthorized"); });
    const failure = await submitGenerate(rpc, fake.host.feedback, { role_id: "rin", prompt: "cat" });
    assert.equal(failure?.kind, "unauthorized");
    assert.equal(getNovelAiState().failure, failure);
    assert.equal(getNovelAiState().submitting, false);
    assert.equal(getNovelAiState().readiness, null, "a rejected token is not the same as an unset one");
  });

  it("a not-configured failure also marks the token as unset, so 生成 stays blocked", async () => {
    const rpc = client(() => { throw new BridgeError("NovelAI token 未配置", "novelai_not_configured"); });
    await submitGenerate(rpc, fake.host.feedback, { role_id: "rin", prompt: "cat" });
    assert.equal(getNovelAiState().readiness?.configured, false);
  });
});

describe("refreshReadiness and loadHistory", () => {
  it("records readiness, and leaves it unknown when the probe itself fails", async () => {
    await refreshReadiness(client(() => ({ configured: false, reason: "placeholder", message: "x" })));
    assert.equal(getNovelAiState().readiness?.reason, "placeholder");
    const before = getNovelAiState();
    await refreshReadiness(client(() => ({ configured: false, reason: "placeholder", message: "x" })));
    assert.equal(getNovelAiState(), before, "an unchanged probe must not publish a new snapshot");
    await refreshReadiness(client(() => { throw new Error("no status"); }));
    assert.equal(getNovelAiState().readiness, null);
  });

  it("reports a history load failure as a toast instead of swallowing it", async () => {
    await loadHistory(client(() => { throw new Error("disk"); }), fake.host.feedback, "rin");
    const toast = fake.feedback.at(-1);
    assert.equal(toast?.tone, "error");
    assert.equal(toast?.options?.detail, "disk");
    // Opted in through the host services: 吟风 fronts it (when the 看板娘 is on); the host maps `true` to its generic line.
    assert.equal(toast?.options?.persona, true);
  });
});
