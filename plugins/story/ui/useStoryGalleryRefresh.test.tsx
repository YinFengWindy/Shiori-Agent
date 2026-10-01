import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginHostServices } from "@shiori/sdk";
import { createFakeHostServices, mountTestComponent } from "@shiori/sdk/testing";
import { useStoryGalleryRefresh } from "./useStoryGalleryRefresh";

test("Story gallery refresh follows plugin events and releases its subscription when closed", async () => {
  type Listener = Parameters<PluginHostServices["onEvent"]>[0];
  const listeners = new Set<Listener>();
  const host: PluginHostServices = {
    ...createFakeHostServices().host,
    onEvent: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
  let refreshes = 0;
  const errors: Array<{ cause: unknown; summary?: string }> = [];
  const refresh = async () => { refreshes++; if (refreshes === 2) throw new Error("gallery failed"); };
  const reportError = (cause: unknown, summary?: string) => { errors.push({ cause, summary }); };
  function Probe({ active }: { active: boolean }) {
    useStoryGalleryRefresh(active, refresh, reportError);
    return null;
  }
  const render = (active: boolean) => <PluginHostServicesProvider services={host}><Probe active={active} /></PluginHostServicesProvider>;
  const emit = async (method: string) => act(async () => {
    for (const listener of listeners) listener({ id: "event", type: "event", method, payload: {} });
  });
  const view = await mountTestComponent(render(true));
  try {
    assert.equal(listeners.size, 1);
    await emit("plugin.other.resource.changed");
    assert.equal(refreshes, 0);
    await emit("plugin.story.resource.changed");
    assert.equal(refreshes, 1);
    await emit("plugin.story.resource.changed");
    assert.equal(errors.length, 1);
    assert.ok(errors[0]?.cause instanceof Error);
    assert.equal(errors[0].cause.message, "gallery failed");
    assert.equal(errors[0].summary, "CG 集刷新失败，请重试");
    await view.render(render(false));
    assert.equal(listeners.size, 0);
    await emit("plugin.story.resource.changed");
    assert.equal(refreshes, 2);
  } finally { await view.cleanup(); }
});
