import assert from "node:assert/strict";
import { it } from "node:test";
import { act, useState } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { RoleCardImportPreviewDialog } from "./RoleCardImportPreview";

it("requires duplicate selection before continuing and keeps compatibility reports hidden", async () => {
  let closed = false;
  function Preview() {
    const [selections, setSelections] = useState<Record<string, string>>({});
    return <RoleCardImportPreviewDialog open sourceUrl="" selections={selections}
      preview={{ import_id: "test", name: "Test", assets: [
        { asset_id: "a", kind: "emotion", name: "neutral", size: 1 },
        { asset_id: "b", kind: "emotion", name: "neutral", size: 1 },
      ], report: { unsupported_macros: ["{{hidden-macro}}"] } }}
      onSelectEmotion={(name, assetId) => setSelections((previous) => ({ ...previous, [name]: assetId }))}
      onClose={() => { closed = true; }} onCancel={() => undefined} />;
  }
  const view = await mountTestComponent(<Preview />);
  try {
    const button = Array.from(view.container.querySelectorAll("button")).find((element) => element.textContent === "继续编辑");
    const choice = view.container.querySelector<HTMLInputElement>('input[value="b"]');
    assert.ok(button && choice);
    assert.equal(button.disabled, true);
    assert.doesNotMatch(view.container.textContent ?? "", /hidden-macro/);
    await act(async () => choice.click());
    assert.equal(button.disabled, false);
    await act(async () => button.click());
    assert.equal(closed, true);
  } finally {
    await view.cleanup();
  }
});

it("shows discarded character book in the import preview", async () => {
  const view = await mountTestComponent(<RoleCardImportPreviewDialog open sourceUrl="" selections={{}}
    preview={{ import_id: "test", name: "Test", report: { discarded_fields: ["character_book"] } }}
    onSelectEmotion={() => undefined} onClose={() => undefined} onCancel={() => undefined} />);
  try {
    assert.match(view.container.textContent ?? "", /未导入内容/);
    assert.match(view.container.textContent ?? "", /character_book/);
    assert.doesNotMatch(view.container.textContent ?? "", /知识库/);
  } finally {
    await view.cleanup();
  }
});
