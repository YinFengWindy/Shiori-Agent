import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useRef, useState } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useSettingsSubsectionMemory } from "../settings/useSettingsSubsectionMemory";
import { useNavigationHistory } from "./useNavigationHistory";
import type { AppMainView } from "../shared/types";
import type { SettingsSectionId } from "../settings/SettingsSidebar";

type HarnessApi = ReturnType<typeof useNavigationHistory> & {
  mainView: AppMainView;
  settingsSection: SettingsSectionId;
  activeSettingsSubsections: Record<string, string>;
};

function Harness({ capture }: { capture: (api: HarnessApi) => void }) {
  const [mainView, setMainView] = useState<AppMainView>({ kind: "chat" });
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId>("models");
  const settingsSubsectionMemory = useSettingsSubsectionMemory();
  const activeRoleIdRef = useRef("");
  const lastNonSettingsViewRef = useRef<AppMainView>({ kind: "chat" });

  const api = useNavigationHistory({
    mainView,
    settingsSection,
    settingsSubsectionMemory,
    activeRoleIdRef,
    lastNonSettingsViewRef,
    roles: [],
    setSettingsSection,
    revealSidebar: () => undefined,
    setMainView,
    applyRoleSnapshot: () => undefined,
  });

  capture({ ...api, mainView, settingsSection, activeSettingsSubsections: settingsSubsectionMemory.activeSubsections });
  return null;
}

async function mountHarness() {
  let latest!: HarnessApi;
  const view = await mountTestComponent(<Harness capture={(api) => { latest = api; }} />);
  // A plain getter would be evaluated once at destructuring time by callers
  // doing `const { api } = await mountHarness()` — a function keeps every
  // read live against whatever the most recent render captured.
  return { view, api: () => latest };
}

describe("useNavigationHistory settings subtab memory (issue #230 AC 4)", () => {
  it("keeps each section's own last subtab independent when switching between sections", async () => {
    const { view, api } = await mountHarness();
    try {
      await act(async () => { api().updateSettingsSubsection("models", "catalog"); });
      await act(async () => { api().updateSettingsSubsection("memory", "embedding"); });
      await act(async () => { api().updateSettingsSubsection("models", "catalog"); });

      assert.equal(api().activeSettingsSubsections.models, "catalog");
      assert.equal(api().activeSettingsSubsections.memory, "embedding");
    } finally { await view.cleanup(); }
  });

  it("restores the exact subtab that was active when the user navigated away, via back/forward", async () => {
    const openRole = async () => true;
    const { view, api } = await mountHarness();
    try {
      // Visit 「插件」, pick the "novelai" subtab, then push a second entry.
      await act(async () => { api().openSettingsWorkspace("plugins"); });
      await act(async () => { api().updateSettingsSubsection("plugins", "novelai"); });
      await act(async () => { api().openSettingsWorkspace("about"); });
      assert.equal(api().settingsSection, "about");

      await act(async () => { await api().navigateHistory("back", openRole); });

      assert.equal(api().settingsSection, "plugins");
      assert.equal(api().activeSettingsSubsections.plugins, "novelai");
    } finally { await view.cleanup(); }
  });

  it("opens a section directly on a given subtab and records it for back/forward", async () => {
    const openRole = async () => true;
    const { view, api } = await mountHarness();
    try {
      await act(async () => { api().openSettingsWorkspace("plugins", { subsectionId: "feishu" }); });
      assert.equal(api().settingsSection, "plugins");
      assert.equal(api().activeSettingsSubsections.plugins, "feishu");

      await act(async () => { api().updateSettingsSubsection("plugins", "novelai"); });
      await act(async () => { api().openSettingsWorkspace("about"); });
      await act(async () => { await api().navigateHistory("back", openRole); });
      assert.equal(api().activeSettingsSubsections.plugins, "novelai");
    } finally { await view.cleanup(); }
  });

  it("switches away and back to a different subtab of the same section across two visits", async () => {
    const openRole = async () => true;
    const { view, api } = await mountHarness();
    try {
      await act(async () => { api().openSettingsWorkspace("plugins"); });
      await act(async () => { api().updateSettingsSubsection("plugins", "novelai"); });
      await act(async () => { api().openSettingsWorkspace("about"); });
      await act(async () => { api().openSettingsWorkspace("plugins"); });
      await act(async () => { api().updateSettingsSubsection("plugins", "qqbot"); });
      await act(async () => { api().openSettingsWorkspace("about"); });

      // Two backs: first lands on the second 「插件」 visit (qqbot), second
      // lands on 「关于」, in between — walk back once more to the first visit.
      await act(async () => { await api().navigateHistory("back", openRole); });
      assert.equal(api().settingsSection, "plugins");
      assert.equal(api().activeSettingsSubsections.plugins, "qqbot");

      await act(async () => { await api().navigateHistory("back", openRole); });
      await act(async () => { await api().navigateHistory("back", openRole); });
      assert.equal(api().settingsSection, "plugins");
      assert.equal(api().activeSettingsSubsections.plugins, "novelai");
    } finally { await view.cleanup(); }
  });
});
