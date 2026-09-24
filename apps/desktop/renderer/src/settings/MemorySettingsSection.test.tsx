import assert from "node:assert/strict";
import { it } from "node:test";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { chooseSelectOption } from "../shared/testing/selectTestActions";
import { createSettingsDraft } from "./testFixtures";

it("MemorySettingsSection retains custom engine values and can reset to the empty default", async () => {
  const view = await mountTestComponent(null);
  const { MemorySettingsSection } = await import("./MemorySettingsSection");
  let draft = createSettingsDraft();
  draft.memory.engine = "custom_memory";
  try {
    await view.render(<MemorySettingsSection draft={draft} subsectionId="general" updateDraft={(mutate) => { draft = mutate(draft); }} />);
    assert.equal(document.querySelector('[role="combobox"]')?.textContent, "custom_memory");
    await chooseSelectOption("记忆引擎", "默认");
    assert.equal(draft.memory.engine, "");
  } finally { await view.cleanup(); }
});
