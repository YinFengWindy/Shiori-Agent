import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleCardExportPreview, RoleCardExportFormat } from "../../../src/bridge/roleCardExportContract";
import { RoleCardExportDetails } from "./RoleCardExportDetails";

const preview: RoleCardExportPreview = {
  export_id: "snapshot", name: "小诗", description: "卡片简介", format: "charx", size: 128, assets: [],
  character: { profile: "完整角色资料".repeat(80), personality: "沉静", behavior_rules: "", response_constraints: "简短回复", nickname: "诗诗" },
};

it("keeps full definitions in individual disclosures and skips empty fields", async () => {
  const view = await mountTestComponent(<RoleCardExportDetails preview={preview} format="charx" busy={false} onSelectFormat={() => undefined} />);
  try {
    assert.match(view.container.textContent ?? "", /小诗诗诗卡片简介/);
    const definitions = Array.from(view.container.querySelectorAll("details"));
    assert.equal(definitions.length, 3);
    assert.equal(definitions[0].open, true);
    assert.equal(definitions[1].open, false);
    assert.equal(definitions[0].querySelector("p")?.textContent, preview.character.profile);
    assert.doesNotMatch(view.container.textContent ?? "", /行为规则/);
    await act(async () => definitions[1].querySelector("summary")?.click());
    assert.equal(definitions[1].open, true);
  } finally { await view.cleanup(); }
});

it("exposes the chosen format and disables every choice while saving", async () => {
  const selections: RoleCardExportFormat[] = [];
  const view = await mountTestComponent(<RoleCardExportDetails preview={preview} format="png" busy={false} onSelectFormat={(format) => selections.push(format)} />);
  try {
    const buttons = Array.from(view.container.querySelectorAll("button"));
    assert.equal(buttons[1].getAttribute("aria-pressed"), "true");
    await act(async () => buttons[2].click());
    assert.deepEqual(selections, ["json"]);
  } finally { await view.cleanup(); }
  const busy = await mountTestComponent(<RoleCardExportDetails preview={preview} format="charx" busy onSelectFormat={(format) => selections.push(format)} />);
  try { assert.ok(Array.from(busy.container.querySelectorAll("button")).every((button) => button.disabled)); }
  finally { await busy.cleanup(); }
});
