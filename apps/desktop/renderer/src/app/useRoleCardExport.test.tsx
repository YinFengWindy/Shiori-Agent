import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { BridgeResponse, DesktopApi } from "../../../src/bridge/shared";
import type { RoleCardExportFormat } from "../../../src/bridge/roleCardExportContract";
import { useRoleCardExport } from "./useRoleCardExport";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => { resolve = complete; });
  return { promise, resolve };
}
function response(format: RoleCardExportFormat = "charx", name = "Role", exportId = "id"): BridgeResponse {
  return { id: "request", type: "response", method: "roles.cardExport.preview", error: null, payload: {
    export_id: exportId, name, description: "简介", format, size: 123, assets: [],
    character: { profile: "资料", personality: "性格", behavior_rules: "规则", response_constraints: "约束", nickname: "昵称" },
  } };
}
async function mountExport(overrides: Partial<Pick<DesktopApi, "invoke" | "saveRoleCardExport">> = {}) {
  let controller!: ReturnType<typeof useRoleCardExport>;
  const requests: Array<Parameters<DesktopApi["invoke"]>[0]> = [];
  const saves: string[] = [];
  function Harness() { controller = useRoleCardExport(); return <output>{controller.state?.preview?.name}</output>; }
  const view = await mountTestComponent(<Harness />);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: {
    invoke: async (request: Parameters<DesktopApi["invoke"]>[0]) => {
      requests.push(request);
      return overrides.invoke ? overrides.invoke(request) : response(request.payload.format as RoleCardExportFormat | undefined);
    },
    saveRoleCardExport: async (id: string) => { saves.push(id); return overrides.saveRoleCardExport ? overrides.saveRoleCardExport(id) : { saved: false }; },
  } });
  return { ...view, requests, saves, get controller() { return controller; } };
}

it("previews the selected role with CHARX by default, then switches formats", async () => {
  const view = await mountExport();
  try {
    await act(async () => view.controller.open("other-role"));
    assert.deepEqual(view.requests[0], { method: "roles.cardExport.preview", payload: { role_id: "other-role", format: "charx" } });
    assert.equal(view.controller.state?.preview?.character.profile, "资料");
    await act(async () => view.controller.selectFormat("json"));
    assert.equal(view.controller.state?.preview?.format, "json");
    assert.ok(view.requests.some((request) => request.method === "roles.cardExport.release"));
  } finally { await view.cleanup(); }
});

for (const change of ["format", "target", "close"] as const) {
  it(`discards an obsolete preview after ${change}`, async () => {
    const slow = deferred<BridgeResponse>();
    let started = 0;
    const view = await mountExport({ invoke: async (request) => {
      if (request.method === "roles.cardExport.release") return response();
      if (started++ === 0) return slow.promise;
      return response("png", "Current", "current");
    } });
    try {
      let pending!: Promise<void>;
      await act(async () => { pending = view.controller.open("first"); });
      await act(async () => {
        if (change === "close") view.controller.close();
        else if (change === "target") await view.controller.open("second", "png");
        else view.controller.selectFormat("png");
      });
      await act(async () => { slow.resolve(response("charx", "Stale", "stale")); await pending; });
      assert.equal(view.controller.state?.preview?.name, change === "close" ? undefined : "Current");
      assert.ok(view.requests.some((request) => request.method === "roles.cardExport.release" && request.payload.export_id === "stale"));
    } finally { await view.cleanup(); }
  });
}

it("prevents duplicate saves and retains the preview after native cancellation", async () => {
  const save = deferred<{ saved: boolean }>();
  const view = await mountExport({ saveRoleCardExport: () => save.promise });
  try {
    await act(async () => view.controller.open("role"));
    let pending!: Promise<void>;
    await act(async () => { pending = view.controller.save(); void view.controller.save(); view.controller.close(); view.controller.selectFormat("json"); });
    assert.deepEqual(view.saves, ["id"]);
    assert.equal(view.controller.state?.status, "saving");
    assert.equal(view.controller.state?.format, "charx");
    await act(async () => { save.resolve({ saved: false }); await pending; });
    assert.equal(view.controller.state?.status, "ready");
    assert.equal(view.controller.state?.error, "");
  } finally { await view.cleanup(); }
});

it("keeps failed saves retryable and closes only after success", async () => {
  let attempts = 0;
  const view = await mountExport({ saveRoleCardExport: async () => {
    if (attempts++ === 0) throw new Error("磁盘已满");
    return { saved: true };
  } });
  try {
    await act(async () => view.controller.open("role"));
    await act(async () => view.controller.save());
    assert.equal(view.controller.state?.error, "磁盘已满");
    await act(async () => view.controller.save());
    assert.equal(view.controller.state, null);
    assert.deepEqual(view.saves, ["id", "id"]);
  } finally { await view.cleanup(); }
});

it("offers preview retry after a backend failure", async () => {
  let attempts = 0;
  const view = await mountExport({ invoke: async () => {
    if (attempts++ === 0) throw new Error("素材缺失");
    return response();
  } });
  try {
    await act(async () => view.controller.open("role"));
    assert.equal(view.controller.state?.status, "error");
    await act(async () => view.controller.retry());
    assert.equal(view.controller.state?.status, "ready");
  } finally { await view.cleanup(); }
});
