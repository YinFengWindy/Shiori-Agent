import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "@shiori/sdk/testing";
import type { RoleProfileDraft } from "../shared/types";
import { RoleCardProfileForm } from "./RoleCardProfileForm";

function DraftForm({ initial, onUpdate }: { initial: RoleProfileDraft; onUpdate: (next: RoleProfileDraft) => void }) {
  const [profile, setProfile] = useState(initial);
  return <RoleCardProfileForm profile={profile} onUpdate={(next) => { setProfile(next); onUpdate(next); }} />;
}

function fieldToggle(container: HTMLElement, title: string) {
  const button = Array.from(container.querySelectorAll("button")).find((item) => item.textContent === title);
  assert.ok(button, `Missing field toggle: ${title}`);
  return button;
}

describe("RoleCardProfileForm", () => {
  it("opens only the setting by default, switches fields and allows all fields to close", async () => {
    const view = await mountTestComponent(<RoleCardProfileForm profile={{}} onUpdate={() => undefined} />);
    try {
      assert.equal(view.container.querySelectorAll("button[aria-expanded='true']").length, 1);
      assert.equal(fieldToggle(view.container, "角色设定").getAttribute("aria-expanded"), "true");
      assert.equal(view.container.querySelectorAll("textarea").length, 1);
      assert.equal(view.container.querySelector("textarea")?.getAttribute("aria-label"), "角色设定");
      assert.equal(view.container.querySelectorAll("p").length, 3);
      assert.equal(view.container.querySelector("p")?.textContent, "未填写");

      await act(async () => fieldToggle(view.container, "性格").click());
      assert.equal(fieldToggle(view.container, "角色设定").getAttribute("aria-expanded"), "false");
      assert.equal(view.container.querySelectorAll("textarea").length, 1);
      assert.equal(view.container.querySelector("textarea")?.getAttribute("aria-label"), "性格");

      await act(async () => fieldToggle(view.container, "性格").click());
      assert.equal(view.container.querySelectorAll("button[aria-expanded='true']").length, 0);
      assert.equal(view.container.querySelectorAll("textarea").length, 0);
    } finally { await view.cleanup(); }
  });

  it("folds optional creation fields without removing their values", async () => {
    let updated: RoleProfileDraft = {};
    const view = await mountTestComponent(<RoleCardProfileForm collapseDetails profile={{ character: { personality: "细心" } }} onUpdate={(next) => { updated = next; }} />);
    try {
      const details = view.container.querySelector("details");
      assert.ok(details);
      assert.equal(details.open, false);
      assert.equal(details.querySelector("summary")?.textContent?.trim(), "更多设定");
      assert.equal(details.querySelector("textarea")?.value, "细心");
      await act(async () => { details.open = true; });
      const personality = details.querySelector("textarea");
      assert.ok(personality);
      await changeInputValue(personality, "细心、耐心");
      assert.equal(updated.character?.personality, "细心、耐心");
    } finally { await view.cleanup(); }
  });

  it("keeps unsaved values and draft summaries while editing each field independently", async () => {
    const profile: RoleProfileDraft = {
      character: { profile: "档案管理员", personality: "细心", behavior_rules: "诚实", response_constraints: "简洁", nickname: "小栞" },
      import_provenance: { format: "chara_card_v2", creator: "作者" },
    };
    let updated = profile;
    const view = await mountTestComponent(<DraftForm initial={profile} onUpdate={(next) => { updated = next; }} />);
    try {
      for (const [title, value] of [["角色设定", "  夜间\n档案管理员  "], ["性格", "耐心"], ["执行规则", "保持诚实"], ["回复约束", "每次回复一句"]]) {
        const toggle = fieldToggle(view.container, title);
        if (toggle.getAttribute("aria-expanded") !== "true") await act(async () => toggle.click());
        const field = view.container.querySelector("textarea");
        assert.ok(field);
        await changeInputValue(field, value);
      }
      assert.equal(updated.character?.profile, "  夜间\n档案管理员  ");
      assert.equal(updated.character?.personality, "耐心");
      assert.equal(updated.character?.behavior_rules, "保持诚实");
      assert.equal(updated.character?.response_constraints, "每次回复一句");
      assert.equal(updated.character?.nickname, "小栞");
      assert.deepEqual(updated.import_provenance, profile.import_provenance);
      assert.ok(Array.from(view.container.querySelectorAll("p")).some((preview) => preview.textContent === "夜间 档案管理员"));

      await act(async () => fieldToggle(view.container, "角色设定").click());
      assert.equal(view.container.querySelector("textarea")?.value, "  夜间\n档案管理员  ");
    } finally {
      await view.cleanup();
    }
  });

  it("updates both collapsed summaries and the open field when the parent resets the draft", async () => {
    const view = await mountTestComponent(<RoleCardProfileForm profile={{ character: { profile: "未保存", personality: "未保存性格" } }} onUpdate={() => undefined} />);
    try {
      await act(async () => fieldToggle(view.container, "性格").click());
      await view.render(<RoleCardProfileForm profile={{ character: { profile: "原始设定", personality: "原始性格" } }} onUpdate={() => undefined} />);
      assert.equal(view.container.querySelector("textarea")?.value, "原始性格");
      assert.equal(view.container.querySelector("p")?.textContent, "原始设定");
    } finally { await view.cleanup(); }
  });
});
