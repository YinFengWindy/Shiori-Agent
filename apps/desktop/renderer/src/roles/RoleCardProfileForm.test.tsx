import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleProfileDraft } from "../shared/types";
import { RoleCardProfileForm } from "./RoleCardProfileForm";

describe("RoleCardProfileForm", () => {
  it("folds optional creation fields without removing their values", async () => {
    const view = await mountTestComponent(<RoleCardProfileForm collapseDetails profile={{ character: { personality: "细心" } }} onUpdate={() => undefined} />);
    try {
      const details = view.container.querySelector("details");
      assert.ok(details);
      assert.equal(details.open, false);
      assert.equal(details.querySelector("textarea")?.value, "细心");
    } finally { await view.cleanup(); }
  });
  it("edits response constraints independently", async () => {
    const profile: RoleProfileDraft = {
      character: { profile: "档案管理员", behavior_rules: "诚实", response_constraints: "简洁" },
    };
    let updated = profile;
    const view = await mountTestComponent(<RoleCardProfileForm profile={profile} onUpdate={(next) => { updated = next; }} />);
    try {
      const label = Array.from(view.container.querySelectorAll("label")).find((item) => item.textContent?.includes("回复约束"));
      const field = label?.querySelector("textarea");
      assert.ok(field);
      assert.equal(field.value, "简洁");
      await changeInputValue(field, "每次回复一句");
      assert.equal(updated.character?.response_constraints, "每次回复一句");
      assert.equal(updated.character?.behavior_rules, "诚实");
      assert.equal(updated.character?.profile, "档案管理员");
    } finally {
      await view.cleanup();
    }
  });
});
