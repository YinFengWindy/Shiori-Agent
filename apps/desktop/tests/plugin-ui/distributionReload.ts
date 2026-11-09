import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import type { SpeechApp } from "./distributionSpeechApp";
import { eventually } from "./packagedApp";
import { record } from "./packagedEvidence";

/** Observe real windows and persisted preferences across unrelated reloads and repeated pet restarts. */
export async function verifySpeechReloadLifecycle(app: SpeechApp) {
  const windows = () => app.app!.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().map((window) => ({ id: window.id, url: window.webContents.getURL() })));
  const owned = async () => (await windows()).filter((window) => window.url.includes("/voice.html") || (window.url.includes("/surface.html") && new URL(window.url).searchParams.get("plugin") === "pet_codex_sprite"));
  const preferences = await app.pluginCall("desktop_pet", "voice.preferences.get");
  const initial = await owned();
  const config = await app.call("plugin.config.get", { plugin_id: "proactive" });
  const values = { ...record(config.values), relationship: !record(config.values).relationship };
  const reloaded = await app.call("plugin.config.set", { plugin_id: "proactive", values, operation_id: randomUUID() });
  assert.ok(Array.isArray(reloaded.reloaded_plugins) && reloaded.reloaded_plugins.includes("proactive"));
  assert.ok(!reloaded.reloaded_plugins.includes("desktop_pet"));
  assert.deepEqual(await owned(), initial, "unrelated reload replaced the pet or its native audio windows");
  const unchanged = await app.call("plugin.config.set", { plugin_id: "proactive", values, operation_id: randomUUID() });
  assert.equal(unchanged.changed, false);
  assert.deepEqual(await owned(), initial, "no-op settings save replaced active native resources");
  assert.deepEqual(await app.pluginCall("desktop_pet", "voice.preferences.get"), preferences);
  await app.evidence.add("unrelated-reload-and-noop-preserve-pet-and-native-windows", { initial, reloaded, unchanged });

  const cycles = [];
  for (let cycle = 0; cycle < 2; cycle++) {
    const disabled = await app.call("plugins.setEnabled", { plugin_id: "desktop_pet", enabled: false, operation_id: randomUUID() });
    await eventually(owned, (items) => items.length === 0, "disabled pet releases surface and native audio windows");
    const unavailable = await app.bridge("desktop_pet.voice.preferences.get");
    assert.ok(unavailable.error);
    const enabled = await app.call("plugins.setEnabled", { plugin_id: "desktop_pet", enabled: true, operation_id: randomUUID() });
    await app.pet();
    const current = await owned();
    assert.equal(current.filter((window) => window.url.includes("/surface.html")).length, 1);
    assert.ok(current.filter((window) => window.url.includes("/voice.html")).length <= 1);
    assert.deepEqual(await app.pluginCall("desktop_pet", "voice.preferences.get"), preferences);
    await app.pluginCall("desktop_pet", "voice.stop", {}, true);
    cycles.push({ disabled, enabled, windows: current });
  }
  await app.evidence.add("repeated-pet-restart-reclaims-native-resources-and-preserves-preferences", { cycles, preferences });
}
