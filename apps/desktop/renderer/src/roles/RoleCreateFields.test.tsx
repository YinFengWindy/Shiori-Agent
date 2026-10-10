import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createEmptyNewRoleForm } from "../app/appState";
import type { NewRoleFormState } from "../shared/types";
import { RoleCreateFields } from "./RoleCreateFields";

function DraftFields({ initial, onUpdate }: {
  initial: NewRoleFormState;
  onUpdate: (next: NewRoleFormState) => void;
}) {
  const [form, setForm] = useState(initial);
  return <RoleCreateFields form={form} disabled={false} onUpdateForm={(update) => {
    setForm((current) => {
      const next = typeof update === "function" ? update(current) : update;
      onUpdate(next);
      return next;
    });
  }} />;
}

function fieldToggle(container: HTMLElement, title: string) {
  const button = Array.from(container.querySelectorAll("button")).find((item) => item.textContent === title);
  assert.ok(button, `Missing field toggle: ${title}`);
  return button;
}

async function openField(container: HTMLElement, title: string) {
  const toggle = fieldToggle(container, title);
  if (toggle.getAttribute("aria-expanded") !== "true") await act(async () => toggle.click());
  assert.equal(container.querySelectorAll("textarea").length, 1);
  const field = container.querySelector<HTMLTextAreaElement>(`textarea[aria-label="${title}"]`);
  assert.ok(field, `Missing field editor: ${title}`);
  return field;
}

describe("RoleCreateFields", () => {
  it("edits all four fields of a blank draft and retains their values when switching", async () => {
    const initial = { ...createEmptyNewRoleForm(), name: "小栞", description: "档案室助手", avatarSource: "avatar.png" };
    let updated: NewRoleFormState = initial;
    const values = [
      ["角色设定", "  夜间\n档案管理员  "],
      ["性格", "细心、耐心"],
      ["执行规则", "保持诚实"],
      ["回复约束", "每次回复一句"],
    ] as const;
    const view = await mountTestComponent(<DraftFields initial={initial} onUpdate={(next) => { updated = next; }} />);
    try {
      assert.deepEqual(Array.from(view.container.querySelectorAll("button"), (button) => button.textContent), values.map(([title]) => title));
      assert.equal(fieldToggle(view.container, "角色设定").getAttribute("aria-expanded"), "true");
      assert.equal(view.container.querySelector("textarea")?.value, "");

      for (const [title, value] of values) await changeInputValue(await openField(view.container, title), value);

      assert.deepEqual(updated, {
        ...initial,
        systemPrompt: "保持诚实",
        profile: {
          ...initial.profile,
          character: {
            ...initial.profile?.character,
            profile: "  夜间\n档案管理员  ",
            personality: "细心、耐心",
            behavior_rules: "保持诚实",
            response_constraints: "每次回复一句",
          },
        },
      });
      assert.ok(Array.from(view.container.querySelectorAll("p")).some((summary) => summary.textContent === "夜间 档案管理员"));
      for (const [title, value] of values) assert.equal((await openField(view.container, title)).value, value);
    } finally { await view.cleanup(); }
  });

  it("maps a legacy system prompt to behavior rules and retains it while editing other fields", async () => {
    const initial: NewRoleFormState = { name: "旧草稿", description: "", systemPrompt: "  保持礼貌\n不编造事实  " };
    let updated = initial;
    const view = await mountTestComponent(<DraftFields initial={initial} onUpdate={(next) => { updated = next; }} />);
    try {
      assert.equal((await openField(view.container, "执行规则")).value, initial.systemPrompt);
      await changeInputValue(await openField(view.container, "角色设定"), "图书管理员");
      await changeInputValue(await openField(view.container, "性格"), "温和");
      assert.equal(updated.profile?.character?.profile, "图书管理员");
      assert.equal(updated.profile?.character?.personality, "温和");
      assert.equal(updated.profile?.character?.behavior_rules, initial.systemPrompt);
      assert.equal(updated.systemPrompt, initial.systemPrompt);

      await changeInputValue(await openField(view.container, "执行规则"), "先核实资料");
      assert.equal(updated.systemPrompt, "先核实资料");
      assert.equal(updated.profile?.character?.behavior_rules, "先核实资料");
    } finally { await view.cleanup(); }
  });

  it("preserves imported metadata and the rest of the creation draft while editing a profile", async () => {
    const initial: NewRoleFormState = {
      name: "小栞",
      description: "导入的档案管理员",
      systemPrompt: "导入时的旧摘要",
      avatarSource: "replacement.png",
      importId: "import-1",
      emotionSelections: { joy: "asset-joy" },
      profile: {
        character: { profile: "档案管理员", personality: "细心", behavior_rules: "诚实", response_constraints: "简洁", nickname: "栞栞" },
        import_provenance: { format: "chara_card_v2", creator: "原作者", tags: ["图书馆"] },
      },
    };
    let updated = initial;
    const view = await mountTestComponent(<DraftFields initial={initial} onUpdate={(next) => { updated = next; }} />);
    try {
      await changeInputValue(await openField(view.container, "性格"), "细心、耐心");
      assert.deepEqual(updated, {
        ...initial,
        systemPrompt: "诚实",
        profile: {
          ...initial.profile,
          character: { ...initial.profile?.character, personality: "细心、耐心" },
        },
      });
      assert.equal((await openField(view.container, "执行规则")).value, "诚实");
    } finally { await view.cleanup(); }
  });

  it("reflects parent resets in the open editor and collapsed summaries", async () => {
    const initial: NewRoleFormState = {
      ...createEmptyNewRoleForm(),
      profile: { character: { profile: "未保存设定", personality: "未保存性格" } },
    };
    const view = await mountTestComponent(<RoleCreateFields form={initial} disabled={false} onUpdateForm={() => undefined} />);
    try {
      await openField(view.container, "性格");
      await view.render(<RoleCreateFields form={{
        ...initial,
        profile: { character: { profile: "原始设定", personality: "原始性格", behavior_rules: "原始规则" } },
      }} disabled={false} onUpdateForm={() => undefined} />);
      assert.equal(view.container.querySelector("textarea")?.getAttribute("aria-label"), "性格");
      assert.equal(view.container.querySelector("textarea")?.value, "原始性格");
      assert.deepEqual(Array.from(view.container.querySelectorAll("p"), (summary) => summary.textContent), ["原始设定", "原始规则", "未填写"]);

      await view.render(<RoleCreateFields form={createEmptyNewRoleForm()} disabled={false} onUpdateForm={() => undefined} />);
      assert.equal(view.container.querySelector("textarea")?.value, "");
      assert.deepEqual(Array.from(view.container.querySelectorAll("p"), (summary) => summary.textContent), ["未填写", "未填写", "未填写"]);
    } finally { await view.cleanup(); }
  });

  it("uses native fieldset disabling for every editor and field toggle while busy", async () => {
    const form = createEmptyNewRoleForm();
    const view = await mountTestComponent(<RoleCreateFields form={form} disabled onUpdateForm={() => undefined} />);
    try {
      const fieldset = view.container.querySelector("fieldset");
      assert.ok(fieldset);
      assert.equal(fieldset.disabled, true);
      const controls = Array.from(view.container.querySelectorAll("button, textarea"));
      assert.equal(controls.length, 5);
      // Browsers disable descendants outside a fieldset's first legend; happy-dom does not model that interaction.
      for (const control of controls) {
        assert.equal(control.closest("fieldset[disabled]"), fieldset);
        assert.equal(control.closest("legend"), null);
      }

      await view.render(<RoleCreateFields form={form} disabled={false} onUpdateForm={() => undefined} />);
      assert.equal(view.container.querySelector("fieldset")?.disabled, false);
    } finally { await view.cleanup(); }
  });
});
