import assert from "node:assert/strict";
import { it } from "node:test";
import { act, createElement } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { memoryPluginId, useConfiguredMemoryPlugin } from "./useConfiguredMemoryPlugin";

it("maps the saved engine to its exact owner", () => {
  assert.equal(memoryPluginId(""), "default_memory");
  assert.equal(memoryPluginId("default"), "default_memory");
  assert.equal(memoryPluginId("akasha"), "akasha");
  assert.equal(memoryPluginId("other"), "other");
});

it("ignores an older settings read after the runtime changes", async () => {
  const pending: Array<(value: unknown) => void> = [];
  const listeners = new Set<(event: { method: string }) => void>();
  function Probe() {
    const selection = useConfiguredMemoryPlugin(true);
    return createElement("p", null, selection.pluginId || selection.status);
  }
  const view = await mountTestComponent(createElement(Probe), { windowGlobals: {
    miraDesktop: {
      readSettings: () => new Promise((resolve) => { pending.push(resolve); }),
      onEvent: (listener: (event: { method: string }) => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    },
  } });
  try {
    await act(async () => { for (const listener of listeners) listener({ method: "runtime.applied" }); });
    assert.equal(pending.length, 2);
    await act(async () => pending[1]({ formData: { memory: { engine: "akasha" } } }));
    assert.match(view.container.textContent ?? "", /akasha/);
    await act(async () => pending[0]({ formData: { memory: { engine: "default" } } }));
    assert.match(view.container.textContent ?? "", /akasha/);
  } finally {
    await view.cleanup();
  }
});
