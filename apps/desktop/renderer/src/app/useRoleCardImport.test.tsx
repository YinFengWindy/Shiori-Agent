import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import type { BridgeResponse } from "../../../src/bridge/shared";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { createEmptyNewRoleForm } from "./appState";
import { useRoleCardImport } from "./useRoleCardImport";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => { resolve = complete; });
  return { promise, resolve };
}

function response(payload: BridgeResponse["payload"] = {}, error: BridgeResponse["error"] = null): BridgeResponse {
  return { id: "request-1", type: "response", method: "roles.cardImport.preview", payload, error };
}

async function mountImport({
  pickRoleCard = async () => "card.charx",
  invoke = async () => response({ import_id: "card-1", name: "Imported", description: "Imported description" }),
}: Partial<Pick<Window["miraDesktop"], "pickRoleCard" | "invoke">> = {}) {
  let controller!: ReturnType<typeof useRoleCardImport>;
  let replaceForm!: React.Dispatch<React.SetStateAction<ReturnType<typeof createEmptyNewRoleForm>>>;
  let currentForm = createEmptyNewRoleForm();
  const feedbackMessages: string[] = [];
  const feedbackDetails: Array<string | undefined> = [];
  const requests: Array<Parameters<Window["miraDesktop"]["invoke"]>[0]> = [];

  function Harness() {
    const [form, setForm] = useState(createEmptyNewRoleForm);
    currentForm = form;
    replaceForm = setForm;
    controller = useRoleCardImport({
      updateNewRoleForm: setForm,
      reportImportError: (message, options) => { feedbackMessages.push(message); feedbackDetails.push(options?.detail); },
    });
    return <output>{controller.roleCardImport.status}:{form.name}</output>;
  }

  const view = await mountTestComponent(<Harness />);
  Object.defineProperty(window, "miraDesktop", {
    configurable: true,
    value: {
      pickRoleCard,
      invoke: async (request: Parameters<Window["miraDesktop"]["invoke"]>[0]) => {
        requests.push(request);
        return invoke(request);
      },
    },
  });
  return {
    ...view, requests, feedbackMessages, feedbackDetails,
    get controller() { return controller; },
    get form() { return currentForm; },
    async replaceForm(next: React.SetStateAction<ReturnType<typeof createEmptyNewRoleForm>>) {
      await act(async () => replaceForm(next));
    },
  };
}

describe("useRoleCardImport", () => {
  it("fills description and structured profile when the preview completes", async () => {
    const profile = { character: { profile: "Biography", response_constraints: "Short replies" } };
    const view = await mountImport({ invoke: async () => response({
      import_id: "card-1", name: "Imported", description: "Imported description", profile,
    }) });
    try {
      await act(async () => view.controller.previewRoleCard());
      assert.equal(view.controller.roleCardImport.status, "ready");
      assert.equal(view.form.importId, "card-1");
      assert.equal(view.form.description, "Imported description");
      assert.deepEqual(view.form.profile, profile);
      assert.deepEqual(view.form.emotionSelections, {});
    } finally { await view.cleanup(); }
  });

  for (const action of ["cancel", "reset"] as const) {
    it(`releases a stale preview after ${action} without restoring the import or overwriting a new form`, async () => {
      const pending = deferred<BridgeResponse>();
      const view = await mountImport({ invoke: async (request) => request.method === "roles.cardImport.preview" ? pending.promise : response() });
      try {
        let previewTask!: Promise<void>;
        await act(async () => { previewTask = view.controller.previewRoleCard(); });
        assert.equal(view.controller.roleCardImport.status, "previewing");
        await act(async () => {
          if (action === "cancel") await view.controller.cancelRoleCardImport();
          else view.controller.clearRoleCardImport();
        });
        await view.replaceForm({ ...createEmptyNewRoleForm(), name: "Later draft", description: "Keep this" });
        await act(async () => {
          pending.resolve(response({ import_id: "stale-card", name: "Stale imported" }));
          await previewTask;
        });
        assert.equal(view.controller.roleCardImport.status, "idle");
        assert.equal(view.form.name, "Later draft");
        assert.equal(view.form.description, "Keep this");
        assert.equal(view.form.importId, undefined);
        assert.deepEqual(view.requests.at(-1), { method: "roles.cardImport.cancel", payload: { import_id: "stale-card" } });
      } finally { await view.cleanup(); }
    });
  }

  it("does not start staging if the picker returns after cancellation", async () => {
    const picker = deferred<string | null>();
    const view = await mountImport({ pickRoleCard: () => picker.promise });
    try {
      let previewTask!: Promise<void>;
      await act(async () => { previewTask = view.controller.previewRoleCard(); });
      await act(async () => view.controller.cancelRoleCardImport());
      await act(async () => { picker.resolve("stale.charx"); await previewTask; });
      assert.equal(view.controller.roleCardImport.status, "idle");
      assert.equal(view.requests.length, 0);
    } finally { await view.cleanup(); }
  });

  it("reports picker rejection and bridge errors while returning to idle", async () => {
    let failPicker = true;
    const view = await mountImport({
      pickRoleCard: async () => {
        if (failPicker) throw new Error("Picker unavailable");
        return "bad.charx";
      },
      invoke: async () => response({}, { code: "invalid_card", message: "Invalid card" }),
    });
    try {
      await act(async () => view.controller.previewRoleCard());
      assert.equal(view.controller.roleCardImport.status, "idle");
      assert.match(view.feedbackMessages.at(-1) ?? "", /Picker unavailable/);
      failPicker = false;
      await act(async () => view.controller.previewRoleCard());
      assert.equal(view.controller.roleCardImport.status, "idle");
      assert.match(view.feedbackMessages.at(-1) ?? "", /Invalid card/);
      assert.equal(view.form.importId, undefined);
    } finally { await view.cleanup(); }
  });

  it("reports a card without character data in plain Chinese and keeps the raw cause as detail", async () => {
    const view = await mountImport({
      pickRoleCard: async () => "photo.png",
      invoke: async () => response({}, { code: "invalid_request", message: "角色卡图片缺少 chara 或 ccv3 metadata" }),
    });
    try {
      await act(async () => view.controller.previewRoleCard());
      assert.equal(view.feedbackMessages.at(-1), "角色导入失败：这张图片里没有找到角色卡数据");
      assert.equal(view.feedbackDetails.at(-1), "角色卡图片缺少 chara 或 ccv3 metadata");
    } finally { await view.cleanup(); }
  });

  it("clears staging immediately and preserves later edits while explicit cancellation awaits the bridge", async () => {
    const pendingCancel = deferred<BridgeResponse>();
    const view = await mountImport({ invoke: async (request) => request.method === "roles.cardImport.cancel"
      ? pendingCancel.promise : response({ import_id: "card-1", name: "Imported" }) });
    try {
      await act(async () => view.controller.previewRoleCard());
      await view.replaceForm((current) => ({ ...current, emotionSelections: { neutral: "asset-1" } }));
      let cancelTask!: Promise<void>;
      await act(async () => { cancelTask = view.controller.cancelRoleCardImport(); });
      assert.equal(view.controller.roleCardImport.status, "idle");
      assert.equal(view.form.importId, undefined);
      assert.equal(view.form.emotionSelections, undefined);
      await view.replaceForm({ ...createEmptyNewRoleForm(), name: "New manual role", description: "Keep my edits" });
      await act(async () => { pendingCancel.resolve(response()); await cancelTask; });
      assert.equal(view.form.name, "New manual role");
      assert.equal(view.form.description, "Keep my edits");
      assert.deepEqual(view.requests.at(-1)?.payload, { import_id: "card-1" });
    } finally { await view.cleanup(); }
  });
});
