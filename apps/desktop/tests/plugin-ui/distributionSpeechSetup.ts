import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { buildPlugin } from "../../../../scripts/build-plugin.mjs";
import { SpeechApp, installGeneratedMicrophone } from "./distributionSpeechApp";
import { eventually } from "./packagedApp";
import { record } from "./packagedEvidence";

/** Install real ZIPs, configure provider-owned assets and select the services through the pet UI. */
export async function prepareSpeech(app: SpeechApp, repository: string, output: string, url: string, assets: { pet: string; reference: string }) {
  await app.launch(); assert.equal((await app.roster()).length, 0);
  await app.settings();
  for (const id of ["sensevoice_asr", "gpt_sovits_tts"]) {
    const archive = await buildPlugin({ plugin: resolve(repository, "plugins", id), output });
    await app.install(archive.archive);
    await app.evidence.add(`installed-${id}`, archive);
  }
  await app.restart(); await app.settings();
  for (const row of await app.roster()) if (row.state === "DISABLED") await app.page!.getByRole("switch", { name: `启用 ${row.display_name}`, exact: true }).click();
  await app.state("ACTIVE");
  await app.pluginCall("sensevoice_asr", "settings.set", { url, device: "cpu", model: "sensevoice" });
  await app.pluginCall("gpt_sovits_tts", "settings.set", { url, version: "v2ProPlus", gpt_weights: "fixture/s1v3.ckpt", sovits_weights: "fixture/s2Gv2ProPlus.pth" });
  await app.call("roles.create", { role_id: "speech-fixture", name: "语音组合验收", system_prompt: "请用普通对话回复。", runtime_config: { mood_catalog: ["happy", "sad"] } });
  const source = await app.pick(assets.reference, "gpt_sovits_tts-audio", "wav");
  const reference = await app.pluginCall("gpt_sovits_tts", "reference.import", { role_id: "speech-fixture", source });
  const voiceReference = { asset: reference.asset, prompt_text: "这是参考音频。", prompt_lang: "zh" };
  await app.pluginCall("gpt_sovits_tts", "role.set", { role_id: "speech-fixture", voice: { text_lang: "zh", speed: 1, default: voiceReference, moods: { happy: voiceReference, sad: voiceReference } } });
  const petSource = await app.pick(assets.pet, "desktop_pet-pets", "zip");
  await app.pluginCall("desktop_pet", "pets.import", { role_id: "speech-fixture", source: petSource });
  await app.pluginCall("desktop_pet", "pets.select", { role_id: "speech-fixture", package_id: "speech-fixture" });
  await app.call("roles.update", { role_id: "speech-fixture", plugin_drafts: { desktop_pet: { enabled: true } } });
  await app.pluginCall("desktop_pet", "sync", { forceVisible: true }, true);
  const page = app.page!;
  await page.getByRole("button", { name: "桌宠 设置", exact: true }).click();
  const capture = await eventually(async () => app.app!.windows().find((candidate) => candidate.url().endsWith("/voice.html")), Boolean, "actual capture renderer");
  assert.ok(capture); await installGeneratedMicrophone(capture);
  await page.getByRole("switch", { name: "桌宠语音", exact: true }).click();
  for (const [name, label] of [["语音识别", "SenseVoiceSmall · CPU"], ["语音合成", "GPT-SoVITS · v2ProPlus"]]) {
    await page.getByRole("combobox", { name, exact: true }).click();
    await page.getByRole("option", { name: label, exact: true }).click();
  }
  await page.getByRole("button", { name: "保存", exact: true }).click();
  const preferences = await eventually(() => app.pluginCall("desktop_pet", "voice.preferences.get"), (value) => value.enabled === true, "pet preferences saved");
  const stored = record(JSON.parse(await readFile(resolve(app.paths.workspace, "plugin-data/desktop_pet/voice-preferences.json"), "utf8")));
  assert.deepEqual(stored, preferences);
  assert.deepEqual(preferences.asr, { plugin_id: "sensevoice_asr", service_id: "asr" });
  assert.deepEqual(preferences.tts, { plugin_id: "gpt_sovits_tts", service_id: "tts" });
  await app.evidence.add("three-plugins-dynamic-service-selection", { providers: await app.roster(), preferences, hardwareInput: "generated WebAudio MediaStream; actual capture pipeline" });
  return app.pet();
}
