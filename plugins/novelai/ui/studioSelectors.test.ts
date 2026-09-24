import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { initialStudioForm, type NovelAiPageState } from "./novelAiPageStore";
import { resolvePresetSize, selectActiveHistoryRecord, selectGenerationBlocked, selectStageView } from "./studioSelectors";
import type { ImageGenerateResult, ImageHistoryRecord } from "./types";

function record(id: string): ImageHistoryRecord {
  return {
    id, created_at: "", role_id: "rin", session_key: "role:rin", mode: "txt2img", prompt: id, negative_prompt: "", model: "m",
    sampler: "", steps: 28, seed: 1, width: 1024, height: 1024, base_image_path: "", output_paths: [`D:/out/${id}.png`],
    wrote_back_to_role: false, role_asset_paths: [],
  };
}

type StageInput = Parameters<typeof selectStageView>[0];
const base: StageInput = {
  submitting: false, failure: null, history: [], selectedRecordId: "", latestResult: null, revealRecordId: "", readiness: null, form: initialStudioForm,
};
const failure = { kind: "network", title: "连不上 NovelAI", message: "", opensSettings: false } as const;
const unset: NovelAiPageState["readiness"] = { configured: false, reason: "placeholder", message: "NovelAI token 引用的环境变量 NOVELAI_TOKEN 未设置" };

describe("selectStageView", () => {
  it("shows the empty motif with no history and no known problem", () => {
    assert.deepEqual(selectStageView(base), { kind: "empty" });
  });

  it("puts work in flight first, framed in the requested aspect", () => {
    const view = selectStageView({ ...base, submitting: true, failure, history: [record("a")], form: { ...initialStudioForm, sizePreset: "landscape" } });
    assert.deepEqual(view, { kind: "generating", aspect: 1216 / 832 });
  });

  it("shows a fresh failure over the picture until it is dismissed", () => {
    assert.deepEqual(selectStageView({ ...base, failure, history: [record("a")] }), { kind: "failure", failure });
  });

  it("shows the selected picture, revealing only the just-generated one", () => {
    const history = [record("new"), record("old")];
    const fresh = selectStageView({ ...base, history, selectedRecordId: "new", revealRecordId: "new" });
    assert.equal(fresh.kind === "image" && fresh.reveal, true);
    const browsing = selectStageView({ ...base, history, selectedRecordId: "old", revealRecordId: "new" });
    assert.equal(browsing.kind === "image" && browsing.path, "D:/out/old.png");
    assert.equal(browsing.kind === "image" && browsing.reveal, false);
  });

  it("an unset token replaces the empty motif, but only annotates an existing picture", () => {
    const empty = selectStageView({ ...base, readiness: unset });
    assert.equal(empty.kind === "failure" && empty.failure.kind, "not-configured");
    const withPicture = selectStageView({ ...base, readiness: unset, history: [record("a")] });
    assert.equal(withPicture.kind, "image");
    assert.equal(withPicture.kind === "image" && withPicture.notice?.kind, "not-configured");
  });

  it("shows a just-generated result before the history refresh lists it, not the previous picture", () => {
    const latestResult: ImageGenerateResult = {
      record_id: "new", created_at: "", mode: "txt2img", model: "m", seed: 1, width: 1, height: 1, output_paths: ["D:/out/new.png"],
      request_path: "", meta_path: "", wrote_back_to_role: false, role_asset_paths: [],
    };
    const view = selectStageView({ ...base, history: [record("old")], selectedRecordId: "new", latestResult, revealRecordId: "new" });
    assert.equal(view.kind === "image" && view.path, "D:/out/new.png");
    assert.equal(view.kind === "image" && view.reveal, true);
  });

  it("falls back to the latest result when history could not be refreshed", () => {
    const latestResult: ImageGenerateResult = {
      record_id: "r", created_at: "", mode: "txt2img", model: "m", seed: 1, width: 1, height: 1, output_paths: ["D:/out/r.png"],
      request_path: "", meta_path: "", wrote_back_to_role: false, role_asset_paths: [],
    };
    const view = selectStageView({ ...base, latestResult, revealRecordId: "r" });
    assert.equal(view.kind === "image" && view.path, "D:/out/r.png");
    assert.equal(view.kind === "image" && view.reveal, true);
  });
});

describe("studio selectors", () => {
  it("selectActiveHistoryRecord prefers the explicit selection, then the newest, then nothing", () => {
    const history = [record("b"), record("a")];
    assert.equal(selectActiveHistoryRecord(history, "a")?.id, "a");
    assert.equal(selectActiveHistoryRecord(history, "")?.id, "b");
    assert.equal(selectActiveHistoryRecord(history, "gone")?.id, "b");
    assert.equal(selectActiveHistoryRecord([], "a"), null);
  });

  it("resolvePresetSize maps presets and waits for both custom sides", () => {
    assert.deepEqual(resolvePresetSize({ sizePreset: "portrait", customWidth: "", customHeight: "" }), [832, 1216]);
    assert.deepEqual(resolvePresetSize({ sizePreset: "custom", customWidth: "640", customHeight: "" }), [1024, 1024]);
    assert.deepEqual(resolvePresetSize({ sizePreset: "custom", customWidth: "640", customHeight: "960" }), [640, 960]);
  });

  it("only a known-unusable token blocks generation", () => {
    assert.equal(selectGenerationBlocked(null), false);
    assert.equal(selectGenerationBlocked({ configured: true, reason: "", message: "" }), false);
    assert.equal(selectGenerationBlocked(unset), true);
  });
});
