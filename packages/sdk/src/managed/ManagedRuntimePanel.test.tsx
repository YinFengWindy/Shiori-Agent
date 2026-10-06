import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "../testing/index";
import { ManagedRuntimePanel } from "./ManagedRuntimePanel";
import type { ManagedRuntimeStatus } from "./useManagedRuntime";

test("import admits only a native selection and forwards the staged path to the owning plugin", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const status: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed" };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload }); return status as T;
  } });
  const { host } = createFakeHostServices();
  let picked = false;
  host.pickFiles = async (options) => {
    picked = true; assert.deepEqual(options.filters[0].extensions, ["7z", "zip"]);
    assert.equal(options.namespace, "sample-runtime");
    return ["C:/private/imports/fixed.zip"];
  };
  const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={host} namespace="sample-runtime" importExtensions={["7z", "zip"]} />);
  try {
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "导入环境包")!;
    await act(async () => button.click());
    assert.equal(picked, true);
    assert.deepEqual(requests.at(-1), { method: "runtime.prepare", payload: { source: "C:/private/imports/fixed.zip" } });
  } finally { await view.cleanup(); }
});
