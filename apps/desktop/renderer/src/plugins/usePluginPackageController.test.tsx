import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useEffect } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { usePluginPackageController } from "./usePluginPackageController";
import type { DesktopInvoke } from "../shared/bridgeInvoke";

test("selecting a ZIP only previews; cancelling never submits trust and failures keep the dialog open", async () => {
  const requests: Parameters<DesktopInvoke>[0][] = [];
  let fail = false;
  const invoke: DesktopInvoke = async (request) => {
    requests.push(request);
    if (fail) throw new Error("disk full");
    return { id: "r", type: "response", method: request.method, error: null, payload: { token: "preview-token", id: "demo", name: "Demo", version: "2.0.0", action: "install" } };
  };
  let controller: ReturnType<typeof usePluginPackageController> | undefined;
  const getPreview = () => controller?.preview;
  function Probe() {
    const value = usePluginPackageController(async (_id, action) => { try { await action(); return true; } catch { return false; } });
    useEffect(() => { controller = value; });
    return null;
  }
  const view = await mountTestComponent(<Probe />, { windowGlobals: { miraDesktop: { invoke, pickFiles: async () => ["native-picked.zip"] } } });
  try {
    await act(async () => { await controller!.pickPackage(); });
    assert.equal(getPreview()?.id, "demo");
    assert.deepEqual(requests.map((request) => request.method), ["plugins.install.preview"]);
    await act(async () => { await controller!.cancel(); });
    assert.equal(getPreview(), null);
    assert.deepEqual(requests.map((request) => request.method), ["plugins.install.preview", "plugins.install.cancel"]);
    await act(async () => { await controller!.pickPackage(); });
    fail = true;
    await act(async () => { await controller!.confirm(); });
    assert.equal(getPreview()?.id, "demo");
    assert.equal(controller!.busy, false);
    assert.equal(requests.at(-1)?.method, "plugins.install.confirm");
  } finally { await view.cleanup(); }
});
