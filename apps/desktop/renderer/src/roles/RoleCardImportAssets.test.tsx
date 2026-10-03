import assert from "node:assert/strict";
import { it } from "node:test";
import { act, useState } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { RoleCardImportAssets } from "./RoleCardImportAssets";

it("selects one of two same-name emotions without selecting ordinary images", async () => {
  let current: Record<string, string> = {};
  function Preview() {
    const [selections, setSelections] = useState(current);
    current = selections;
    return <RoleCardImportAssets assets={[
      { asset_id: "a", kind: "emotion", name: "neutral", size: 1 },
      { asset_id: "b", kind: "emotion", name: "neutral", size: 1 },
      { asset_id: "c", kind: "avatar", name: "main", size: 1 },
    ]} selections={selections} onSelectEmotion={(name, assetId) => setSelections((previous) => ({ ...previous, [name]: assetId }))} />;
  }
  const view = await mountTestComponent(<Preview />);
  try {
    const radios = view.container.querySelectorAll<HTMLInputElement>('input[type="radio"]');
    assert.equal(radios.length, 2);
    assert.equal(radios[0].checked, false);
    assert.equal(radios[1].checked, false);
    await act(async () => radios[1].click());
    assert.deepEqual(current, { neutral: "b" });
    assert.equal(radios[0].checked, false);
    assert.equal(radios[1].checked, true);
    await act(async () => radios[0].click());
    assert.deepEqual(current, { neutral: "a" });
    assert.equal(radios[1].checked, false);
  } finally {
    await view.cleanup();
  }
});
