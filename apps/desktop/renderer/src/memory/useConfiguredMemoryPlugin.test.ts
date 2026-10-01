import assert from "node:assert/strict";
import { it } from "node:test";
import { act, createElement } from "react";
import { mountTestComponent } from "@shiori/sdk/testing";
import { memoryPluginId, readMemoryPluginId, useConfiguredMemoryPlugin } from "./useConfiguredMemoryPlugin";

it("maps the saved engine to its exact owner", () => {
  assert.equal(memoryPluginId(""), "default_memory");
  assert.equal(memoryPluginId("default"), "default_memory");
  assert.equal(memoryPluginId("other"), "other");
});

it("ignores an older settings read after the runtime changes", async () => {
  const pending: Array<{ resolve: (value: unknown) => void; reject: (error: Error) => void }> = [];
  const listeners = new Set<(event: { method: string; payload: { changed?: boolean } }) => void>();
  function Probe() {
    const selection = useConfiguredMemoryPlugin(true);
    return createElement("p", null, selection.pluginId || selection.status);
  }
  const view = await mountTestComponent(createElement(Probe), { windowGlobals: {
    miraDesktop: {
      readSettings: () => new Promise((resolve, reject) => { pending.push({ resolve, reject }); }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: true } }); });
    assert.equal(pending.length, 2);
    await act(async () => pending[1].resolve({ formData: { memory: { engine: "default" } } }));
    assert.match(view.container.textContent ?? "", /default_memory/);
    await act(async () => pending[0].reject(new Error("stale read failed")));
    assert.match(view.container.textContent ?? "", /default_memory/);
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
      readSettings: async () => ({ formData: { memory: { engine: "default" } } }),
      onEvent: (listener: (event: { method: string; payload: { changed?: boolean } }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    assert.match(view.container.textContent ?? "", /default_memory/);
    const before = observed.length;
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied", payload: { changed: false } }); });
    assert.ok(observed.slice(before).every((value) => value === "ready:default_memory"));
    assert.equal(observed.at(-1), "ready:default_memory");
  } finally {
    await view.cleanup();
  }
});

it("times out a stalled settings read", async () => {
  await assert.rejects(readMemoryPluginId(() => new Promise(() => undefined), 1), /设置读取超时/);
});
