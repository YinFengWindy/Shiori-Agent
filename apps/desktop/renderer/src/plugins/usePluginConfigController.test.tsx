import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { PluginConfigValues } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createPluginHostConfig } from "./pluginHostConfig";
import { usePluginConfigController } from "./usePluginConfigController";
import { pluginConfigChanges } from "./pluginConfigChanges";

/** A preload bridge over one in-memory `plugin.config` table. */
function configBridge(table: PluginConfigValues) {
  let stored = { ...table };
  return {
    onEvent: () => () => undefined,
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      if (method === "plugin.config.set") stored = { ...(payload.values as PluginConfigValues) };
      else if (method !== "plugin.config.get") throw new Error(method);
      return { id: "1", type: "response", method, error: null, payload: { plugin_id: payload.plugin_id, schema: {}, values: { ...stored }, env_status: {}, generation: 1 } };
    },
  };
}

const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

test("the settings page and the plugin's host.config see each other's saves", async () => {
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: configBridge({ nsfw_enabled: false, add_quality_tags: false }) } });
  let controller!: ReturnType<typeof usePluginConfigController>;
  function SettingsPage() {
    controller = usePluginConfigController("novelai");
    return null;
  }
  try {
    await view.render(<SettingsPage />);
    await settle();
    assert.deepEqual(controller.draft, { nsfw_enabled: false, add_quality_tags: false });

    // A plugin save refreshes the host's config state.
    const config = createPluginHostConfig("novelai");
    await act(async () => { await config.save({ nsfw_enabled: true }); });
    await settle();
    assert.deepEqual(controller.draft, { nsfw_enabled: true, add_quality_tags: false });

    // And a save on the settings page reaches the plugin's subscription.
    const heard: PluginConfigValues[] = [];
    const unsubscribe = config.subscribe((values) => heard.push(values));
    await act(async () => controller.updateDraft((current) => ({ ...current, add_quality_tags: true })));
    assert.equal(controller.savePhase, "saving", "the quiet period is still unsaved");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
    unsubscribe();
    assert.deepEqual(heard, [{ nsfw_enabled: true, add_quality_tags: true }]);
  } finally { await view.cleanup(); }
});

test("a departed save response must not discard a newer draft after returning", async () => {
  let stored = { text: "saved" };
  let release!: () => void;
  const oldResponse = new Promise<void>((resolve) => { release = resolve; });
  const writes: string[] = [];
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: {
    onEvent: () => () => {},
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      let values = { ...stored };
      if (method === "plugin.config.set") {
        values = { ...(payload.values as typeof stored) };
        stored = values;
        writes.push(values.text);
        if (writes.length === 1) await oldResponse;
      }
      return { id: "probe", type: "response", method, error: null, payload: {
        plugin_id: payload.plugin_id, schema: {}, values, env_status: {}, generation: 1,
      } };
    },
  } } });
  let controller!: ReturnType<typeof usePluginConfigController>;
  function Form() { controller = usePluginConfigController("demo"); return null; }
  try {
    await view.render(<Form />);
    await act(async () => controller.updateDraft(() => ({ text: "departing" })));
    await view.render(null);
    assert.deepEqual(writes, ["departing"]);
    await view.render(<Form />);
    await act(async () => controller.updateDraft(() => ({ text: "new draft" })));
    assert.equal(controller.draft?.text, "new draft");
    await act(async () => release());
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    assert.equal(controller.draft?.text, "new draft");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
    assert.deepEqual(writes, ["departing", "new draft"]);
    assert.equal(stored.text, "new draft");
    assert.equal(controller.savePhase, "idle");
  } finally { release(); await view.cleanup(); }
});



for (const pending of ["queued", "inflight", "unknown", "error"] as const) {
  test(`external saves preserve local drafts and transaction identity while ${pending}`, async () => {
    const failed = pending === "unknown" || pending === "error";
    let stored: PluginConfigValues = { text: "saved" };
    const writes: Array<{ text: unknown; id: unknown }> = [];
    let release!: () => void;
    const flight = new Promise<void>((resolve) => { release = resolve; });
    let localAttempts = 0;
    let controller!: ReturnType<typeof usePluginConfigController>;
    function Form() { controller = usePluginConfigController("demo"); return null; }
    const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: {
      invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
        if (method === "plugin.config.set") {
          const values = payload.values as PluginConfigValues;
          writes.push({ text: values.text, id: payload.operation_id });
          if (values.text === "local") {
            localAttempts++;
            if (pending === "inflight" && localAttempts === 1) await flight;
            if (failed && localAttempts === 1) return { id: "save", type: "response", method,
              error: { code: pending === "unknown" ? "bridge_timeout" : "runtime_apply_failed", message: "save failed" }, payload: {} };
          }
          stored = { ...values };
        }
        return { id: "response", type: "response", method, error: null, payload: {
          plugin_id: payload.plugin_id, schema: {}, values: { ...stored }, env_status: {}, generation: 1,
        } };
      },
    } } });
    try {
      await view.render(<Form />);
      await act(async () => controller.updateDraft(() => ({ text: "local" })));
      if (pending !== "queued") await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
      const config = createPluginHostConfig("demo");
      await act(async () => { await config.save({ text: "external" }); });
      await settle();
      assert.equal(controller.draft?.text, "local");
      assert.equal(controller.savePhase, failed ? pending : "saving");
      if (failed) await act(async () => controller.retrySave());
      else if (pending === "inflight") await act(async () => release());
      else await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
      assert.equal(controller.draft?.text, "local");
      assert.equal(controller.savePhase, "idle");
      assert.deepEqual(await config.get(), { text: "local" });
      const local = writes.filter((entry) => entry.text === "local");
      assert.equal(local.length, failed ? 2 : 1);
      if (failed) assert.equal(local[0].id, local[1].id);
      await act(async () => { await config.save({ text: "idle external" }); });
      await settle();
      assert.equal(controller.draft?.text, "idle external", "idle external changes still synchronize");
      await act(async () => controller.updateDraft(() => ({ text: "local" })));
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
      assert.deepEqual(await config.get(), { text: "local" }, "a previously saved value can be submitted again after an external change");
    } finally { release(); await view.cleanup(); }
  });
}

for (const readBeforeEdit of [true, false]) test(`an external read started ${readBeforeEdit ? "before" : "after"} editing cannot overwrite the later save`, async () => {
  let stored = { text: "saved" };
  let holdReads = false;
  let release!: () => void;
  const reading = new Promise<void>((resolve) => { release = resolve; });
  let controller!: ReturnType<typeof usePluginConfigController>;
  function Form() { controller = usePluginConfigController("demo"); return null; }
  const view = await mountTestComponent(null, { windowGlobals: { miraDesktop: {
    invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      if (method === "plugin.config.set") stored = { ...(payload.values as typeof stored) };
      const values = { ...stored };
      if (method === "plugin.config.get" && holdReads) await reading;
      return { id: "response", type: "response", method, error: null, payload: {
        plugin_id: "demo", schema: {}, values, env_status: {}, generation: 1,
      } };
    },
  } } });
  try {
    await view.render(<Form />);
    holdReads = true; stored = { text: "external" };
    if (!readBeforeEdit) await act(async () => controller.updateDraft(() => ({ text: "new local" })));
    await act(async () => pluginConfigChanges.publish("demo", stored, {}));
    if (readBeforeEdit) await act(async () => controller.updateDraft(() => ({ text: "new local" })));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
    assert.equal(controller.savePhase, "idle");
    await act(async () => release());
    assert.equal(controller.draft?.text, "new local");
    assert.equal(stored.text, "new local");
  } finally { release(); await view.cleanup(); }
});


test("an external response in the edit's render batch preserves the draft before enqueue runs", async () => {
  const bridge = configBridge({ text: "saved" });
  let controller!: ReturnType<typeof usePluginConfigController>;
  function Form() { controller = usePluginConfigController("demo"); return null; }
  const view = await mountTestComponent(<Form />, { windowGlobals: { miraDesktop: bridge } });
  try {
    const config = createPluginHostConfig("demo");
    await act(async () => {
      controller.updateDraft(() => ({ text: "same-batch draft" }));
      await config.save({ text: "external" });
    });
    assert.equal(controller.draft?.text, "same-batch draft");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 420)); });
    assert.deepEqual(await config.get(), { text: "same-batch draft" });
  } finally { await view.cleanup(); }
});
