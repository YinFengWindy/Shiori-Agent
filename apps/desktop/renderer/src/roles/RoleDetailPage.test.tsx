import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { changeInputValue, chooseSelectOption, mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createEmptyRoleForm } from "../app/appState";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { createSettingsDraft } from "../settings/testFixtures";
import type { RoleRecord } from "@shiori/plugin-sdk";
import type { RoleFormState } from "../shared/types";
import { RoleDetailPage } from "./RoleDetailPage";

type PageProps = Parameters<typeof RoleDetailPage>[0];

function pageElement(overrides: Partial<PageProps> = {}) {
  return (
    <RoleDetailPage
      activeRole={null}
      activeRoleId="role-1"
      bridgeReady
      previewAvatar={null}
      currentMood=""
      moodIllustrationUrl=""
      roleForm={createEmptyRoleForm()}
      roleFormDirty={false}
      savingRole={false}
      onBackToList={() => undefined}
      onGoToChat={() => undefined}
      onOpenAssetsPage={() => undefined}
      onRoleModelChanged={() => undefined}
      onUpdateRoleForm={() => undefined}
      onResetRoleForm={() => undefined}
      onSaveRole={() => undefined}
      {...overrides}
    />
  );
}

function renderPage(overrides: Partial<PageProps> = {}) {
  return renderToStaticMarkup(pageElement(overrides));
}

function DraftDetailPage({ onSave }: { onSave: (form: RoleFormState) => void }) {
  const [form, setForm] = useState(profileForm);
  return pageElement({
    roleForm: form,
    roleFormDirty: form !== profileForm,
    onUpdateRoleForm: setForm,
    onResetRoleForm: () => setForm(profileForm),
    onSaveRole: () => onSave(form),
  });
}

const profileForm: RoleFormState = {
  ...createEmptyRoleForm(),
  name: "Mira",
  profile: {
    character: {
      profile: "A meticulous archivist.",
      personality: "Calm and precise.",
      behavior_rules: "Keep focus.",
    },
  },
};

const role: RoleRecord = {
  id: "role-1", name: "Mira", description: "", system_prompt: "", runtime_config: {},
  avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
  illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
  created_at: "", updated_at: "",
};

describe("RoleDetailPage", () => {
  it("opens on the profile tab with the setting grouped into sections", () => {
    const markup = renderPage({ roleForm: profileForm, roleFormDirty: true });

    assert.match(markup, /资料/);
    assert.match(markup, /记忆/);
    assert.doesNotMatch(markup, /知识库/);
    assert.match(markup, /能力/);
    assert.doesNotMatch(markup, /主动推送/);
    // Tabs read 资料 / 记忆 / 能力 / 账号; accounts live only in their own tab.
    assert.match(markup, /资料<\/button>.*记忆<\/button>.*能力<\/button>.*账号<\/button>/);
    assert.doesNotMatch(markup, /添加账号/);
    assert.doesNotMatch(markup, /渠道绑定/);
    assert.match(markup, /aria-current="page"[^>]*>.*资料/);
    assert.match(markup, /角色设定/);
    assert.match(markup, /性格/);
    assert.match(markup, /执行规则/);
    assert.doesNotMatch(markup, /data-testid="role-channel-config"/);
  });

  it("puts labeled 重置 and 保存 buttons in the header, off until the draft changes", () => {
    const clean = renderPage();
    assert.match(clean, /data-testid="save-role-button"[^>]*disabled=""[^>]*>.*保存<\/button>/);
    assert.match(clean, /data-testid="reset-role-button"[^>]*disabled=""[^>]*>.*重置<\/button>/);

    const dirty = renderPage({ roleFormDirty: true });
    assert.doesNotMatch(dirty, /data-testid="save-role-button"[^>]*disabled=""/);
    assert.doesNotMatch(dirty, /data-testid="reset-role-button"[^>]*disabled=""/);
  });

  it("saves the folded draft through the existing toolbar and resets all profile fields", async () => {
    let saved: RoleFormState | undefined;
    const view = await mountTestComponent(<DraftDetailPage onSave={(form) => { saved = form; }} />);
    const button = (label: string) => {
      const found = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label);
      assert.ok(found, `Missing button: ${label}`);
      return found;
    };
    try {
      await act(async () => button("执行规则").click());
      const editor = view.container.querySelector<HTMLTextAreaElement>("textarea[aria-label='执行规则']");
      assert.ok(editor);
      await changeInputValue(editor, "新的执行规则");
      await act(async () => button("性格").click());
      await act(async () => button("保存").click());
      assert.ok(saved);
      assert.equal(saved.systemPrompt, "新的执行规则");
      assert.equal(saved.profile?.character?.behavior_rules, "新的执行规则");
      assert.equal(saved.profile?.character?.profile, profileForm.profile?.character?.profile);

      await act(async () => button("重置").click());
      assert.equal(button("保存").disabled, true);
      await act(async () => button("执行规则").click());
      assert.equal(view.container.querySelector<HTMLTextAreaElement>("textarea[aria-label='执行规则']")?.value, "Keep focus.");
    } finally { await view.cleanup(); }
  });

  it("keeps save unavailable while the bridge is down, and shows 保存中 while saving", () => {
    assert.match(renderPage({ roleFormDirty: true, bridgeReady: false }), /data-testid="save-role-button"[^>]*disabled=""/);
    const saving = renderPage({ roleFormDirty: true, savingRole: true });
    assert.match(saving, /data-testid="save-role-button"[^>]*data-saving="true"[^>]*disabled=""[^>]*>.*保存中…<\/button>/);
  });

  it("saves and resets proactive edits through the shared role draft across tab switches", async () => {
    setPluginEnabledSnapshot([]);
    let saved: RoleFormState | undefined;
    const view = await mountTestComponent(<DraftDetailPage onSave={(form) => { saved = form; }} />, {
      windowGlobals: { miraDesktop: { readSettings: async () => ({ formData: createSettingsDraft() }) } },
    });
    const button = (label: string) => {
      const found = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label);
      assert.ok(found, `Missing button: ${label}`);
      return found;
    };
    try {
      await act(async () => button("能力").click());
      assert.ok(view.container.querySelector('[data-testid="role-proactive-config"]'));
      const toggle = view.container.querySelector<HTMLButtonElement>('[role="switch"][aria-label="主动推送"]');
      assert.ok(toggle);
      await act(async () => toggle.click());
      await chooseSelectOption("推送策略", "低打扰");
      await act(async () => button("执行参数").click());
      const steps = Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "每次推送最大步数")?.querySelector("input");
      assert.ok(steps);
      await changeInputValue(steps, "48");
      assert.equal(view.container.querySelector('[role="switch"][aria-label="空闲活动"]'), null);
      const driftSteps = Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "空闲活动最大步数")?.querySelector("input");
      const driftInterval = Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "空闲活动最小间隔（小时）")?.querySelector("input");
      assert.ok(driftSteps);
      assert.ok(driftInterval);
      await changeInputValue(driftSteps, "9");
      await changeInputValue(driftInterval, "5");
      await act(async () => button("资料").click());
      await act(async () => button("保存").click());
      assert.deepEqual(saved, { ...profileForm, proactiveEnabled: true, proactiveProfile: "quiet", proactiveAgentMaxSteps: 48, proactiveDriftMaxSteps: 9, proactiveDriftMinIntervalHours: 5 });

      await act(async () => button("能力").click());
      assert.equal(view.container.querySelector('[aria-label="主动推送"]')?.getAttribute("aria-checked"), "true");
      assert.equal(view.container.querySelector('[aria-label="推送策略"]')?.textContent, "低打扰");
      assert.equal(button("执行参数").getAttribute("aria-expanded"), "false");
      await act(async () => button("执行参数").click());
      assert.equal(Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "每次推送最大步数")?.querySelector("input")?.value, "48");

      await act(async () => button("重置").click());
      assert.equal(button("保存").disabled, true);
      assert.equal(view.container.querySelector('[aria-label="主动推送"]')?.getAttribute("aria-checked"), "false");
      assert.equal(view.container.querySelector('[aria-label="推送策略"]')?.textContent, "日常");
      assert.equal(Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "空闲活动最大步数")?.querySelector("input")?.value, String(profileForm.proactiveDriftMaxSteps));
      assert.equal(Array.from(view.container.querySelectorAll("label"))
        .find((label) => label.textContent === "空闲活动最小间隔（小时）")?.querySelector("input")?.value, String(profileForm.proactiveDriftMinIntervalHours));
    } finally {
      await view.cleanup();
      resetPluginEnabledStateForTests();
    }
  });

  it("offers 去聊天 for a loaded role while the bridge is up", () => {
    assert.match(renderPage({ activeRole: role }), /data-testid="role-detail-go-to-chat"[^>]*>.*去聊天/);
    assert.doesNotMatch(renderPage({ activeRole: role }), /data-testid="role-detail-go-to-chat"[^>]*disabled/);
    assert.match(renderPage({ activeRole: role, bridgeReady: false }), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
    assert.match(renderPage(), /data-testid="role-detail-go-to-chat"[^>]*disabled=""/);
  });

  it("shows the current mood and a visible 更换形象 action in the character header", () => {
    const markup = renderPage({ activeRole: role, currentMood: "平静" });
    assert.match(markup, /data-testid="role-detail-mood"[^>]*>.*平静/);
    assert.match(markup, /data-testid="open-role-assets-button"[^>]*>.*更换形象<\/button>/);
  });

  it("draws the mood portrait behind the header when there is one", () => {
    assert.match(renderPage({ moodIllustrationUrl: "asset://smile.png" }), /data-has-portrait="true"/);
    assert.match(renderPage(), /data-has-portrait="false"/);
  });

  it("shows the role's models on the profile tab for a loaded role", () => {
    assert.match(renderPage({ activeRole: role }), /data-testid="role-model-section"/);
    assert.match(renderPage({ activeRole: role }), /聊天模型/);
  });
});
