import assert from "node:assert/strict";
import { it } from "node:test";
import { act, createElement } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { memoryPluginId, readMemoryPluginId, useConfiguredMemoryPlugin } from "./useConfiguredMemoryPlugin";

it("maps the saved engine to its exact owner", () => {
  assert.equal(memoryPluginId(""), "default_memory");
  assert.equal(memoryPluginId("default"), "default_memory");
  assert.equal(memoryPluginId("akasha"), "akasha");
  assert.equal(memoryPluginId("other"), "other");
});

it("ignores an older settings read after the runtime changes", async () => {
  const pending: Array<(value: unknown) => void> = [];
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  function Probe() {
    const selection = useConfiguredMemoryPlugin(true);
    return createElement("p", null, selection.pluginId || selection.status);
  }
  const view = await mountTestComponent(createElement(Probe), { windowGlobals: {
    miraDesktop: {
      readSettings: () => new Promise((resolve) => { pending.push(resolve); }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: true } }); });
    assert.equal(pending.length, 2);
    await act(async () => pending[1]({ formData: { memory: { engine: "akasha" } } }));
    assert.match(view.container.textContent ?? "", /akasha/);
    await act(async () => pending[0]({ formData: { memory: { engine: "default" } } }));
    assert.match(view.container.textContent ?? "", /akasha/);
  } finally {
    await view.cleanup();
  }
});

it("keeps the same ready selection through a no-op runtime publication", async () => {
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  const observed: string[] = [];
  function Probe() {
    const selection = useConfiguredMemoryPlugin(true);
    observed.push(`${selection.status}:${selection.pluginId}`);
    return createElement("p", null, selection.pluginId || selection.status);
  }
  const view = await mountTestComponent(createElement(Probe), { windowGlobals: {
    miraDesktop: {
      readSettings: async () => ({ formData: { memory: { engine: "akasha" } } }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /akasha/);
    const before = observed.length;
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: false } }); });
    assert.ok(observed.slice(before).every((value) => value === "ready:akasha"));
    assert.equal(observed.at(-1), "ready:akasha");
  } finally {
    await view.cleanup();
  }
});

it("times out a stalled settings read", async () => {
  await assert.rejects(readMemoryPluginId(() => new Promise(() => undefined), 1), /设置读取超时/);
});
