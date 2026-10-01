import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginConfigValues } from "../contract/hostServices";
import { createFakeHostServices } from "./fakeHostServices";

test("the fake host records every call in order and keeps the plugin's config in memory", async () => {
  const fake = createFakeHostServices({ config: { nsfw_enabled: false }, pickFiles: async () => ["/staged/pet.zip"] });
  const heard: PluginConfigValues[] = [];
  fake.host.config.subscribe((values) => heard.push(values));

  fake.host.feedback.error("生成失败", { persona: "network" });
  assert.deepEqual(await fake.host.pickFiles({ namespace: "pets", maxFileBytes: 1, filters: [] }), ["/staged/pet.zip"]);
  assert.deepEqual(await fake.host.config.save({ nsfw_enabled: true }), { nsfw_enabled: true });
  assert.equal(fake.host.assets.url("C:/a.png"), "fake-asset://C:/a.png");

  assert.deepEqual(fake.calls.map((call) => call.service), ["feedback", "pickFiles", "config.save", "assets.url"]);
  assert.deepEqual(fake.feedback, [{ service: "feedback", tone: "error", message: "生成失败", options: { persona: "network" } }]);
  assert.deepEqual(fake.config(), { nsfw_enabled: true });
  assert.deepEqual(heard, [{ nsfw_enabled: true }]);
});

test("a replaced save can fail, leaving the stored config and subscribers untouched", async () => {
  const fake = createFakeHostServices({ config: { preset: 0 }, saveConfig: async () => { throw new Error("preset 必须是整数"); } });
  const heard: PluginConfigValues[] = [];
  fake.host.config.subscribe((values) => heard.push(values));
  await assert.rejects(fake.host.config.save({ preset: "x" }), /必须是整数/);
  assert.deepEqual(fake.config(), { preset: 0 });
  assert.deepEqual(heard, []);
});

test("emit delivers a bridge event to onEvent listeners until they unsubscribe", () => {
  const fake = createFakeHostServices();
  const methods: string[] = [];
  const unsubscribe = fake.host.onEvent((event) => methods.push(event.method));
  fake.emit({ id: "1", type: "event", method: "plugin.story.gallery", payload: {} });
  unsubscribe();
  fake.emit({ id: "2", type: "event", method: "plugin.story.gallery", payload: {} });
  assert.deepEqual(methods, ["plugin.story.gallery"]);
});
