import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import {
  backToStudio,
  clearFailure,
  getNovelAiState,
  openPromptTagLibrary,
  openPromptTagWorkspaceSection,
  refreshRoles,
  resetNovelAiPageStoreForTests,
  selectBlockedReasonForNovelAiPage,
  selectRecord,
  setPromptTagSection,
  updateStudioForm,
  useNovelAiPageStore,
} from "./novelAiPageStore";

type Snapshot = ReturnType<typeof useNovelAiPageStore>;

function fakeMiraDesktop(roles: Array<{ id: string; name: string }>) {
  return {
    invoke: async ({ method }: { method: string }) => {
      if (method !== "roles.list") {
        return { id: "1", type: "response", method, error: { code: "unknown_method", message: "" }, payload: null };
      }
      return { id: "1", type: "response", method, error: null, payload: { roles } };
    },
  };
}

/** Mounts two independent sibling subscribers — mirrors the host mounting `NovelAIPage` and `NovelAIPageSidebar` separately. */
async function mountTwoMountPoints() {
  const rendersA: Snapshot[] = [];
  const rendersB: Snapshot[] = [];
  function MountPointA() {
    rendersA.push(useNovelAiPageStore());
    return null;
  }
  function MountPointB() {
    rendersB.push(useNovelAiPageStore());
    return null;
  }
  const view = await mountTestComponent(<><MountPointA /><MountPointB /></>);
  return { view, rendersA, rendersB };
}

const failure = { kind: "network", title: "连不上 NovelAI", message: "", opensSettings: false } as const;

describe("novelAiPageStore (issue #226 gap A's 'real complication')", () => {
  it("propagates view/promptTagSection changes to every mount point, whichever one made the change", async () => {
    resetNovelAiPageStoreForTests();
    const { view, rendersA, rendersB } = await mountTwoMountPoints();
    try {
      // The sidebar opens the library.
      act(() => { openPromptTagLibrary(); });
      assert.equal(rendersA.at(-1)?.view, "prompt-tags", "the page mount point must see the sidebar's navigation");
      assert.equal(rendersB.at(-1)?.promptTagSection, "list");

      // The page opens an entry.
      act(() => { openPromptTagWorkspaceSection("detail"); });
      assert.equal(rendersB.at(-1)?.promptTagSection, "detail", "the sidebar must see the page's navigation");

      // 提示词库 again from the sidebar lands back on the list.
      act(() => { openPromptTagLibrary(); });
      assert.equal(rendersA.at(-1)?.promptTagSection, "list");

      act(() => { backToStudio(); });
      assert.equal(rendersA.at(-1)?.view, "studio");
      assert.equal(rendersB.at(-1)?.view, "studio");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });

  it("openPromptTagWorkspaceSection forces the library view only for 'list'", () => {
    resetNovelAiPageStoreForTests();
    openPromptTagWorkspaceSection("create");
    assert.equal(getNovelAiState().view, "studio");
    assert.equal(getNovelAiState().promptTagSection, "create");
    openPromptTagWorkspaceSection("list");
    assert.equal(getNovelAiState().view, "prompt-tags");
    setPromptTagSection("detail");
    assert.equal(getNovelAiState().promptTagSection, "detail");
    resetNovelAiPageStoreForTests();
  });

  it("selectBlockedReasonForNovelAiPage fails open before the roster has loaded, then reflects the real roster", async () => {
    resetNovelAiPageStoreForTests();
    const originalWindow = (globalThis as { window?: { miraDesktop?: unknown } }).window;
    try {
      (globalThis as { window?: { miraDesktop?: unknown } }).window = { miraDesktop: fakeMiraDesktop([]) };
      assert.equal(selectBlockedReasonForNovelAiPage(desktopPluginHostServices), null, "must fail open before the roster is known");
      await refreshRoles(desktopPluginHostServices);
      assert.equal(
        selectBlockedReasonForNovelAiPage(desktopPluginHostServices),
        "请先创建至少一个角色，再进入生图。",
        "zero roles once loaded must block navigation with the pre-migration message, verbatim",
      );

      resetNovelAiPageStoreForTests();
      (globalThis as { window?: { miraDesktop?: unknown } }).window = { miraDesktop: fakeMiraDesktop([{ id: "role-1", name: "Ada" }]) };
      await refreshRoles(desktopPluginHostServices);
      assert.equal(selectBlockedReasonForNovelAiPage(desktopPluginHostServices), null, "a non-empty roster must allow navigation");
    } finally {
      (globalThis as { window?: unknown }).window = originalWindow;
      resetNovelAiPageStoreForTests();
    }
  });
});

describe("novelAiPageStore form and canvas state", () => {
  it("keeps the form across view switches and ignores edits that change nothing", () => {
    resetNovelAiPageStoreForTests();
    updateStudioForm({ prompt: "1girl, library" });
    openPromptTagLibrary();
    backToStudio();
    assert.equal(getNovelAiState().form.prompt, "1girl, library", "a half-written prompt survives the library round trip");

    const before = getNovelAiState();
    updateStudioForm({ prompt: "1girl, library" });
    assert.equal(getNovelAiState(), before, "an unchanged edit must not publish a new snapshot");
    resetNovelAiPageStoreForTests();
  });

  it("switching the generation role drops the previous role's failure and fresh result, other edits keep them", () => {
    resetNovelAiPageStoreForTests({ form: { ...getNovelAiState().form, roleId: "rin" }, failure, revealRecordId: "rec-1" });

    updateStudioForm({ prompt: "smile" });
    assert.equal(getNovelAiState().failure, failure, "editing the prompt keeps the failure on screen");

    updateStudioForm({ roleId: "natsu" });
    assert.equal(getNovelAiState().failure, null);
    assert.equal(getNovelAiState().revealRecordId, "");
    resetNovelAiPageStoreForTests();
  });

  it("clearFailure and selectRecord dismiss the canvas failure; clearFailure is a no-op when clean", () => {
    resetNovelAiPageStoreForTests();
    const clean = getNovelAiState();
    clearFailure();
    assert.equal(getNovelAiState(), clean, "nothing to clear must not produce a new snapshot");

    resetNovelAiPageStoreForTests({ failure });
    selectRecord("rec-2");
    assert.equal(getNovelAiState().failure, null, "picking a history item brings the picture back");
    assert.equal(getNovelAiState().selectedRecordId, "rec-2");
    resetNovelAiPageStoreForTests();
  });
});
