import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { BridgeError } from "../../../apps/desktop/renderer/src/shared/bridgeInvoke";
import { getFeedbackSnapshot, resetFeedback } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import { pluginHostFeedback } from "../../../apps/desktop/renderer/src/plugins/pluginHostFeedback";
import { loadHistory, refreshReadiness, submitGenerate } from "./novelAiGeneration";
import { getNovelAiState, resetNovelAiPageStoreForTests } from "./novelAiPageStore";

function client(handler: (method: string) => unknown): PluginRpcClient {
  return { ...createPluginRpcClient("fixture"), call: async <T,>(method: string) => handler(method) as T };
}

const result = {
  record_id: "rec-1", created_at: "", mode: "txt2img", model: "m", seed: 1, width: 1024, height: 1024, output_paths: ["D:/out/1.png"],
  request_path: "", meta_path: "", wrote_back_to_role: false, role_asset_paths: [],
};
const historyRecord = {
  id: "rec-1", created_at: "", role_id: "rin", session_key: "", mode: "txt2img", prompt: "", negative_prompt: "", model: "m", sampler: "",
  steps: 0, seed: 1, width: 1024, height: 1024, base_image_path: "", output_paths: ["D:/out/1.png"], wrote_back_to_role: false, role_asset_paths: [],
};

afterEach(() => {
  resetNovelAiPageStoreForTests();
  resetFeedback();
});

describe("submitGenerate", () => {
  it("flips submitting synchronously, then publishes the result as the revealed, selected record", async () => {
    const rpc = client((method) => (method === "generate" ? { result } : { records: [historyRecord] }));
    const pending = submitGenerate(rpc, pluginHostFeedback, { role_id: "rin", prompt: "cat" });
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
    const failure = await submitGenerate(rpc, pluginHostFeedback, { role_id: "rin", prompt: "cat" });
    assert.equal(failure?.kind, "unauthorized");
    assert.equal(getNovelAiState().failure, failure);
    assert.equal(getNovelAiState().submitting, false);
    assert.equal(getNovelAiState().readiness, null, "a rejected token is not the same as an unset one");
  });

  it("a not-configured failure also marks the token as unset, so 生成 stays blocked", async () => {
    const rpc = client(() => { throw new BridgeError("NovelAI token 未配置", "novelai_not_configured"); });
    await submitGenerate(rpc, pluginHostFeedback, { role_id: "rin", prompt: "cat" });
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
    await loadHistory(client(() => { throw new Error("disk"); }), pluginHostFeedback, "rin");
    const toast = getFeedbackSnapshot().at(-1);
    assert.equal(toast?.tone, "error");
    assert.equal(toast?.detail, "disk");
    // Opted in through the host services: 吟风 fronts it (when the 看板娘 is on).
    assert.equal(toast?.persona, "generic");
  });
});
