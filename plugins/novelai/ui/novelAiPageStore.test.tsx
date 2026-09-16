import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import {
  __getSnapshotForTests,
  backToStudio,
  clearError,
  loadHistory,
  openPromptTagLibrary,
  openPromptTagWorkspaceSection,
  refreshRoles,
  resetNovelAiPageStoreForTests,
  selectActiveHistoryRecord,
  selectBlockedReasonForNovelAiPage,
  setActiveRoleId,
  setPromptTagSection,
  submitGenerate,
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

/** Mounts two independent sibling components, each subscribing to the shared store — mirrors the host mounting `NovelAIPage` and `NovelAIPageSidebar` as two separate mount points. */
async function mountTwoMountPoints() {
  const rendersA: Snapshot[] = [];
  const rendersB: Snapshot[] = [];

  function MountPointA() {
    const state = useNovelAiPageStore();
    rendersA.push(state);
    return null;
  }
  function MountPointB() {
    const state = useNovelAiPageStore();
    rendersB.push(state);
    return null;
  }

  const view = await mountTestComponent(
    <>
      <MountPointA />
      <MountPointB />
    </>,
  );
  return { view, rendersA, rendersB };
}

describe("novelAiPageStore (issue #226 gap A's 'real complication')", () => {
  it("propagates view/promptTagSection changes to every mount point, whichever one made the change", async () => {
    resetNovelAiPageStoreForTests();
    const { view, rendersA, rendersB } = await mountTwoMountPoints();
    try {
      assert.equal(rendersA.at(-1)?.view, "studio");
      assert.equal(rendersB.at(-1)?.view, "studio");

      // Simulates the Sidebar mount point opening the prompt-tag library.
      act(() => { openPromptTagLibrary(); });
      assert.equal(rendersA.at(-1)?.view, "prompt-tags", "the Page mount point must see the Sidebar's navigation");
      assert.equal(rendersB.at(-1)?.view, "prompt-tags");

      // Simulates the Page mount point's PromptTagLibraryPage navigating to "detail" after opening an entry.
      act(() => { openPromptTagWorkspaceSection("detail"); });
      assert.equal(rendersA.at(-1)?.promptTagSection, "detail");
      assert.equal(rendersB.at(-1)?.promptTagSection, "detail", "the Sidebar mount point must see the Page's navigation");

      // Simulates the Sidebar's own "list"/"create" buttons (no forced view change, already in prompt-tags).
      act(() => { setPromptTagSection("list"); });
      assert.equal(rendersB.at(-1)?.promptTagSection, "list");

      // Simulates the Sidebar's "返回生图" button.
      act(() => { backToStudio(); });
      assert.equal(rendersA.at(-1)?.view, "studio");
      assert.equal(rendersB.at(-1)?.view, "studio");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });

  it("openPromptTagWorkspaceSection forces the view to prompt-tags only when the section is 'list'", async () => {
    resetNovelAiPageStoreForTests();
    const { view, rendersA } = await mountTwoMountPoints();
    try {
      act(() => { backToStudio(); });
      act(() => { openPromptTagWorkspaceSection("create"); });
      // "create" does not force the view switch on its own in the original
      // behaviour — only "list" does (see NovelAIPage's pre-#226 onOpenSection).
      assert.equal(rendersA.at(-1)?.view, "studio");
      assert.equal(rendersA.at(-1)?.promptTagSection, "create");

      act(() => { openPromptTagWorkspaceSection("list"); });
      assert.equal(rendersA.at(-1)?.view, "prompt-tags");
      assert.equal(rendersA.at(-1)?.promptTagSection, "list");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });

  it("relays activeRoleId from the page's effect so the sidebar mount point (which the host never gives it directly) can read it", async () => {
    resetNovelAiPageStoreForTests();
    const { view, rendersB } = await mountTwoMountPoints();
    try {
      act(() => { setActiveRoleId("role-1"); });
      assert.equal(rendersB.at(-1)?.activeRoleId, "role-1");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });

  it("setActiveRoleId is a no-op (no new snapshot, no re-render) when the value does not actually change", async () => {
    resetNovelAiPageStoreForTests();
    const { view, rendersA } = await mountTwoMountPoints();
    try {
      act(() => { setActiveRoleId("role-1"); });
      const afterFirstSet = rendersA.length;
      const snapshotBefore = rendersA.at(-1);

      act(() => { setActiveRoleId("role-1"); });
      assert.equal(rendersA.length, afterFirstSet, "an unchanged activeRoleId must not trigger a re-render");
      assert.equal(rendersA.at(-1), snapshotBefore, "the snapshot reference must be unchanged too");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });

  it("setActiveRoleId clears error/latestResult only when the role actually changes", async () => {
    resetNovelAiPageStoreForTests();
    const failingClient: PluginRpcClient = { ...createPluginRpcClient("fixture"), call: async () => { throw new Error("boom"); } };
    await loadHistory(failingClient, "role-1");
    assert.notEqual(__getSnapshotForTests().error, "");

    // A fresh store's activeRoleId defaults to "", so switching to "role-1"
    // does count as a change — the reset below is expected to fire.
    setActiveRoleId("role-1");
    assert.equal(__getSnapshotForTests().error, "");
    resetNovelAiPageStoreForTests();
  });

  it("selectBlockedReasonForNovelAiPage fails open (returns null) before the roster has ever loaded, then reflects the real roster once it has", async () => {
    resetNovelAiPageStoreForTests();
    const originalWindow = (globalThis as { window?: { miraDesktop?: unknown } }).window;
    try {
      (globalThis as { window?: { miraDesktop?: unknown } }).window = { miraDesktop: fakeMiraDesktop([]) };
      assert.equal(selectBlockedReasonForNovelAiPage(desktopPluginHostServices), null, "must fail open before the roster is known");

      // selectBlockedReasonForNovelAiPage kicks a refresh off in the background; wait for it.
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

  it("submitGenerate publishes submitting/latestResult/history so both mount points see the same result", async () => {
    resetNovelAiPageStoreForTests();
    const client: PluginRpcClient = { ...createPluginRpcClient("fixture"),
      call: async <T,>(method: string): Promise<T> => {
        if (method === "generate") {
          return { result: { record_id: "rec-1", created_at: "", mode: "txt2img", model: "m", seed: null, width: 1, height: 1, output_paths: [], request_path: "", meta_path: "", wrote_back_to_role: false, role_asset_paths: [] } } as T;
        }
        if (method === "history") {
          return { records: [{ id: "rec-1", created_at: "", role_id: "role-1", session_key: "", mode: "txt2img", prompt: "", negative_prompt: "", model: "m", sampler: "", steps: 0, seed: null, width: 1, height: 1, base_image_path: "", output_paths: [], wrote_back_to_role: false, role_asset_paths: [] }] } as T;
        }
        throw new Error(`unexpected method ${method}`);
      },
    };
    const { view, rendersA, rendersB } = await mountTwoMountPoints();
    try {
      let submitting!: Promise<void>;
      act(() => { submitting = submitGenerate(client, { role_id: "role-1", prompt: "a cat" }); });
      assert.equal(rendersA.at(-1)?.submitting, true, "submitting must flip true synchronously before the RPC resolves");

      await act(async () => { await submitting; });
      assert.equal(rendersA.at(-1)?.submitting, false);
      assert.equal(rendersA.at(-1)?.latestResult?.record_id, "rec-1");
      assert.equal(rendersA.at(-1)?.selectedRecordId, "rec-1");
      assert.equal(rendersB.at(-1)?.history.length, 1, "the other mount point must see the same refreshed history");
    } finally {
      await view.cleanup();
      resetNovelAiPageStoreForTests();
    }
  });
});

describe("novelAiPageStore selectors and error clearing", () => {
  it("selectActiveHistoryRecord prefers the explicit selection, then the newest, then nothing", () => {
    const history = [
      { id: "b", prompt: "newest" },
      { id: "a", prompt: "older" },
    ] as unknown as Parameters<typeof selectActiveHistoryRecord>[0];
    assert.equal(selectActiveHistoryRecord(history, "a")?.id, "a");
    // No explicit selection falls back to the newest, not to null.
    assert.equal(selectActiveHistoryRecord(history, "")?.id, "b");
    // A selection that is no longer in history must not blank the preview.
    assert.equal(selectActiveHistoryRecord(history, "gone")?.id, "b");
    assert.equal(selectActiveHistoryRecord([], "a"), null);
  });

  it("clearError drops the banner, and is a no-op when there is nothing to drop", async () => {
    resetNovelAiPageStoreForTests();
    const before = __getSnapshotForTests();
    // Nothing to clear: the snapshot identity must not change, or every
    // subscriber re-renders for nothing.
    clearError();
    assert.equal(__getSnapshotForTests(), before, "clearError on a clean store must not produce a new snapshot");

    const failingClient: PluginRpcClient = { ...createPluginRpcClient("fixture"), call: async () => { throw new Error("boom"); } };
    await loadHistory(failingClient, "role-1");
    assert.notEqual(__getSnapshotForTests().error, "");

    // Submitting an emptied prompt takes this path. Losing it was a silent
    // regression when `useImageStudioState` was dissolved (#226 spec review).
    clearError();
    assert.equal(__getSnapshotForTests().error, "");
    resetNovelAiPageStoreForTests();
  });
});