import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { PluginHostServicesProvider } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { desktopPluginHostServices, type PluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { useStoryGalleryRefresh } from "./useStoryGalleryRefresh";

test("Story gallery refresh follows plugin events and releases its subscription when closed", async () => {
  type Listener = Parameters<PluginHostServices["onEvent"]>[0];
  const listeners = new Set<Listener>();
  const host: PluginHostServices = {
    ...desktopPluginHostServices,
    listRoles: async () => [], pickImages: async () => [], pickFiles: async () => [],
    onEvent: (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
  };
  let refreshes = 0;
  const errors: string[] = [];
  const refresh = async () => { refreshes++; if (refreshes === 2) throw new Error("gallery failed"); };
  const reportError = (message: string) => { errors.push(message); };
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
    assert.deepEqual(errors, ["gallery failed"]);
    await view.render(render(false));
    assert.equal(listeners.size, 0);
    await emit("plugin.story.resource.changed");
    assert.equal(refreshes, 2);
  } finally { await view.cleanup(); }
});
