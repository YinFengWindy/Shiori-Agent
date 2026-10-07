import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "../testing/index";
import { ManagedRuntimePanel } from "./ManagedRuntimePanel";
import type { ManagedRuntimeStatus } from "./useManagedRuntime";

test("import admits only a native selection and forwards the staged path to the owning plugin", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const status: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", reclaimable: 0 };
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

test("removal needs a stopped runtime and a destructive confirmation", async () => {
  const requests: string[] = [];
  const installed: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: true, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", reclaimable: 0 };
  async function mount(status: ManagedRuntimeStatus) {
    const client = createFakePluginClient({ call: async <T,>(method: string) => { requests.push(method); return status as T; } });
    const fake = createFakeHostServices();
    const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={fake.host} namespace="sample-runtime" importExtensions={["zip"]} />);
    const removeButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "删除环境")!;
    return { view, removeButton, renders: fake.uiRenders };
  }
  const running = await mount({ ...installed, phase: "ready", running: true });
  try { assert.equal(running.removeButton.disabled, true); } finally { await running.view.cleanup(); }
  const { view, removeButton, renders } = await mount(installed);
  try {
    assert.equal(removeButton.disabled, false);
    await act(async () => removeButton.click());
    assert.equal(renders.ConfirmDialog.at(-1)?.destructive, true);
    assert.equal(requests.includes("runtime.remove"), false);
    const dialog = view.container.querySelector('[role="dialog"]')!;
    const confirm = Array.from(dialog.querySelectorAll("button")).find((item) => item.textContent === "删除环境")!;
    await act(async () => confirm.click());
    assert.equal(requests.at(-1), "runtime.remove");
    assert.equal(view.container.querySelector('[role="dialog"]'), null);
  } finally { await view.cleanup(); }
});

test("a kept download cache can be removed without an installation", async () => {
  const requests: string[] = [];
  const status: ManagedRuntimeStatus = { phase: "error", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", reclaimable: 10 * 1024 ** 3 };
  const client = createFakePluginClient({ call: async <T,>(method: string) => { requests.push(method); return status as T; } });
  const { host, uiRenders } = createFakeHostServices();
  const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={host} namespace="sample-runtime" importExtensions={["zip"]} />);
  try {
    const removeButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "删除环境");
    assert.ok(removeButton && !removeButton.disabled);
    await act(async () => removeButton.click());
    assert.match(uiRenders.ConfirmDialog.at(-1)?.description ?? "", /10\.00 GiB/);
  } finally { await view.cleanup(); }
});
