import assert from "node:assert/strict";
import { it } from "node:test";
import type { AffectionStagePrompt } from "./affectionStagePrompts";
import { changedStagePrompts, selectedStagePromptRow, stagePromptRequest, stagePromptRows, stagePromptTexts } from "./stagePromptSelectors";

const stages: AffectionStagePrompt[] = [
  { stage: "陌生", prompt: "客气。", default: "客气。", overridden: false },
  { stage: "熟悉", prompt: "嘴硬心软。", default: "放松。", overridden: true },
];

it("treats a blank field or the default's own text as the default, like the backend", () => {
  const texts = { ...stagePromptTexts(stages), 陌生: "  " };
  assert.deepEqual(stagePromptRows(stages, texts).map((row) => row.overridden), [false, true]);
  assert.deepEqual(stagePromptRequest(stages, texts), { 陌生: null, 熟悉: "嘴硬心软。" });
  assert.deepEqual(stagePromptRequest(stages, { 陌生: " 客气。\n", 熟悉: "放松。" }), { 陌生: null, 熟悉: null });
});

it("trims an override, so text differing only in surrounding whitespace saves nothing new", () => {
  assert.deepEqual(
    stagePromptRequest(stages, { 陌生: "冷淡。\n", 熟悉: "嘴硬心软。 " }),
    stagePromptRequest(stages, { 陌生: "冷淡。", 熟悉: "嘴硬心软。" }),
  );
});

it("writes only the stages that differ from what is stored", () => {
  const saved = stagePromptRequest(stages, stagePromptTexts(stages));
  assert.deepEqual(changedStagePrompts(stagePromptRequest(stages, { 陌生: "冷淡。", 熟悉: "嘴硬心软。" }), saved), { 陌生: "冷淡。" });
  assert.deepEqual(changedStagePrompts(stagePromptRequest(stages, { 陌生: "客气。", 熟悉: "" }), saved), { 熟悉: null });
});

it("shows the picked stage, else the role's current one, else the lowest, keeping every stage's edited text", () => {
  const rows = stagePromptRows(stages, { 陌生: "冷淡。", 熟悉: "嘴硬心软。" });
  assert.equal(selectedStagePromptRow(rows, null)?.stage, "陌生");
  assert.equal(selectedStagePromptRow(rows, null, "熟悉")?.stage, "熟悉");
  assert.equal(selectedStagePromptRow(rows, "陌生", "熟悉")?.text, "冷淡。");
  assert.equal(selectedStagePromptRow(rows, "挚爱", "厌恶")?.stage, "陌生");
  assert.equal(selectedStagePromptRow([], "陌生"), undefined);
});
