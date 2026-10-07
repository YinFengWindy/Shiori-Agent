import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "../testing/index";
import { ManagedRuntimePanel } from "./ManagedRuntimePanel";
import type { ManagedRuntimeStatus } from "./useManagedRuntime";

const footprint = { reclaimable: 0, staging: false, location: "D:/Envs/sample-runtime", customized: true, required: 30 * 1024 ** 3, required_import: 20 * 1024 ** 3, free: 100 * 1024 ** 3, removable: false, relocatable: true };

test("import picks the original path and forwards it uncopied to the owning plugin", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const status: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", ...footprint };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload }); return status as T;
  } });
  const { host, calls } = createFakeHostServices({ pickFilePaths: async (options) => {
    assert.deepEqual(options.filters[0].extensions, ["7z", "zip"]);
    return ["E:/Downloads/fixed.7z"];
  } });
  const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={host} importExtensions={["7z", "zip"]} />);
  try {
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "导入环境包")!;
    await act(async () => button.click());
    assert.deepEqual(calls.map((call) => call.service), ["pickFilePaths"]);
    assert.deepEqual(requests.at(-1), { method: "runtime.prepare", payload: { source: "E:/Downloads/fixed.7z" } });
  } finally { await view.cleanup(); }
});

test("the location shows the checked space and changes or resets only while nothing is kept", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  async function mount(status: ManagedRuntimeStatus) {
    const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
      requests.push({ method, payload }); return status as T;
    } });
    const fake = createFakeHostServices({ pickDirectory: async () => "D:/Envs" });
    const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={fake.host} importExtensions={["zip"]} />);
    const buttons = Array.from(view.container.querySelectorAll("button"));
    const space = Array.from(view.container.querySelectorAll("span")).find((item) => item.textContent?.includes("剩余"))!;
    return {
      view, space, calls: fake.calls,
      change: buttons.find((item) => item.textContent === "更改位置")!,
      reset: buttons.find((item) => item.textContent === "恢复默认"),
      remove: buttons.find((item) => item.textContent === "删除环境"),
    };
  }
  const empty: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", ...footprint, free: 8 * 1024 ** 3 };
  // Installed: only the free space, never flagged; leftovers block both location actions and are removable.
  const installed = await mount({ ...empty, installed: true, removable: true, relocatable: false });
  try {
    assert.equal(installed.space.textContent, "剩余 8.0 GiB");
    assert.doesNotMatch(installed.space.className, /text-danger-text/);
    assert.equal(installed.change.disabled, true);
    assert.equal(installed.reset?.disabled, true);
    assert.ok(installed.remove && !installed.remove.disabled);
  } finally { await installed.view.cleanup(); }
  const { view, change, reset, remove, space, calls } = await mount(empty);
  try {
    assert.match(view.container.textContent ?? "", /D:\/Envs\/sample-runtime/);
    assert.equal(space.textContent, "下载需约 30.0 GiB · 导入需约 20.0 GiB · 剩余 8.0 GiB");
    assert.match(space.className, /text-danger-text/);
    assert.equal(remove, undefined);
    assert.equal(change.disabled, false);
    await act(async () => change.click());
    assert.deepEqual(calls.map((call) => call.service), ["pickDirectory"]);
    assert.deepEqual(requests.at(-1), { method: "runtime.relocate", payload: { directory: "D:/Envs" } });
    await act(async () => reset!.click());
    assert.deepEqual(requests.at(-1), { method: "runtime.relocate", payload: {} });
  } finally { await view.cleanup(); }
  const standard = await mount({ ...empty, customized: false });
  try { assert.equal(standard.reset, undefined); } finally { await standard.view.cleanup(); }
});

test("removal needs a stopped runtime and a destructive confirmation", async () => {
  const requests: string[] = [];
  const installed: ManagedRuntimeStatus = { phase: "stopped", running: false, installed: true, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", ...footprint, removable: true, relocatable: false };
  async function mount(status: ManagedRuntimeStatus) {
    const client = createFakePluginClient({ call: async <T,>(method: string) => { requests.push(method); return status as T; } });
    const fake = createFakeHostServices();
    const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={fake.host} importExtensions={["zip"]} />);
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
  const status: ManagedRuntimeStatus = { phase: "error", running: false, installed: false, busy: false, error: "", item: "", received: 0, total: 0, revision: "fixed", ...footprint, reclaimable: 10 * 1024 ** 3, removable: true, relocatable: false };
  const client = createFakePluginClient({ call: async <T,>(method: string) => { requests.push(method); return status as T; } });
  const { host, uiRenders } = createFakeHostServices();
  const view = await mountTestComponent(<ManagedRuntimePanel client={client} host={host} importExtensions={["zip"]} />);
  try {
    const removeButton = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "删除环境");
    assert.ok(removeButton && !removeButton.disabled);
    await act(async () => removeButton.click());
    assert.match(uiRenders.ConfirmDialog.at(-1)?.description ?? "", /10\.00 GiB/);
  } finally { await view.cleanup(); }
});
