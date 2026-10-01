import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { BridgeError, PluginHostServicesProvider } from "@shiori/sdk";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@shiori/sdk/testing";
import { createStoryBridgeClient } from "./storyBridgeClient";
import { useStoryController } from "./useStoryController";

test("Story list failures retain a separate safe cause and loading failures reach their caller", async () => {
  const failure = new BridgeError("本地服务处理失败", "internal_error", { detail: "database unavailable token=private-value" });
  const client = createStoryBridgeClient(createFakePluginClient({ call: async () => { throw failure; } }));
  const { host } = createFakeHostServices();
  let state!: ReturnType<typeof useStoryController>;
  function Probe() { state = useStoryController(client); return null; }
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><Probe /></PluginHostServicesProvider>);
  try {
    assert.equal(state.error, "剧情列表加载失败，请重试");
    assert.match(state.errorDetail ?? "", /database unavailable/);
    assert.doesNotMatch(state.errorDetail ?? "", /private-value/);
    await act(async () => { await assert.rejects(state.loadStory("story-1"), (error) => error === failure); });
    assert.equal(state.busy, false);
  } finally { await view.cleanup(); }
});
