import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginBridgeError } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import { releasePreview } from "./previewCleanup";

test("release tolerates only known disposed clients and reports other cleanup failures to host feedback", async () => {
  const host = createFakeHostServices();
  let failure: unknown = new PluginBridgeError("disposed in another locale", "plugin_unavailable", { reason: "context_disposed" });
  const client = createFakePluginClient({ background: { call: async () => { throw failure; } } });
  await releasePreview(client, "preview", host.host.feedback);
  assert.equal(host.feedback.length, 0);
  failure = new PluginBridgeError("后台不可用", "plugin_unavailable", { detail: "transport closed" });
  await releasePreview(client, "preview", host.host.feedback);
  assert.equal(host.feedback.length, 1);
  assert.match(host.feedback[0].options?.detail ?? "", /后台不可用\ntransport closed/);
  failure = { message: "TypeError: native stop failed" };
  await releasePreview(client, "preview", host.host.feedback);
  assert.match(host.feedback[1].options?.detail ?? "", /^native stop failed$/);
  failure = new PluginBridgeError("插件通信已处置", "plugin_unavailable");
  await releasePreview(client, "preview", host.host.feedback);
  assert.equal(host.feedback.length, 3, "a translated message is not a disposal marker");
});
