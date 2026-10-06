import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import type { Page } from "playwright";
import { DevelopmentApp } from "./packagedDevelopmentApp";
import { eventually } from "./packagedApp";
import { record } from "./packagedEvidence";

/** Production application driver using public plugin contexts and native surfaces. */
export class SpeechApp extends DevelopmentApp {
  async launch() {
    await super.launch();
    await this.app!.evaluate(({ ipcMain }) => {
      const observations: Array<{ kind: string; sender: number; value: unknown }> = [];
      Reflect.set(globalThis, "speechNative", observations);
      for (const kind of ["capture-ready", "capture-error", "playback-started", "playback-finished", "playback-error"]) {
        ipcMain.on(`desktop:voice-${kind}`, (event, value: unknown) => observations.push({ kind, sender: event.sender.id, value }));
      }
    });
    await this.page!.evaluate(() => {
      const events: unknown[] = []; Reflect.set(window, "speechBridge", events);
      window.miraDesktop.onEvent((event) => { if (event.method.startsWith("chat.")) events.push(event); });
    });
  }
  async roster() {
    const response = await this.call("plugins.list"); assert.ok(Array.isArray(response.plugins));
    return response.plugins.map(record).filter((row) => ["sensevoice_asr", "gpt_sovits_tts"].includes(String(row.id)));
  }
  async pluginCall(pluginId: string, name: string, payload: Record<string, unknown> = {}, background = false) {
    const owner = randomUUID();
    const { generation } = await this.call("plugins.communication.open", { plugin_id: pluginId, owner });
    try {
      return await this.call(background ? "plugins.communication.call" : `plugin.${pluginId}.${name}`, background
        ? { plugin_id: pluginId, owner, generation, target: pluginId, name, payload }
        : { ...payload, __plugin_context: { plugin_id: pluginId, generation } });
    } finally { await this.call("plugins.communication.close", { plugin_id: pluginId, owner, generation }); }
  }
  async pick(path: string, namespace: string, extension: string) {
    await this.app!.evaluate(({ dialog }, path) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [path] }); }, path);
    const sources = await this.page!.evaluate(({ namespace, extension }) => window.miraDesktop.pickFiles({ namespace, filters: [{ name: "Fixture", extensions: [extension] }], multiple: false, maxFileBytes: 32 * 1024 * 1024 }), { namespace, extension });
    assert.equal(sources.length, 1); return sources[0];
  }
  async pet() {
    const page = await eventually(async () => this.app!.windows().find((candidate) => {
      const url = new URL(candidate.url()); return url.pathname.endsWith("/surface.html") && url.searchParams.get("plugin") === "desktop_pet";
    }), Boolean, "real desktop pet surface");
    assert.ok(page); await page.getByLabel("桌宠", { exact: true }).waitFor(); return page;
  }
  async nativeEvents() {
    const events: unknown = await this.app!.evaluate(() => Reflect.get(globalThis, "speechNative"));
    assert.ok(Array.isArray(events)); return events.map(record);
  }
  async chatEvents() {
    const events: unknown = await this.page!.evaluate(() => Reflect.get(window, "speechBridge"));
    assert.ok(Array.isArray(events)); return events.map(record);
  }
  async speak(pet: Page) {
    const ready = (await this.nativeEvents()).filter((event) => event.kind === "capture-ready").length;
    await pet.evaluate(() => window.miraDesktop.surface.postToBackground({ kind: "voice.gesture", gesture: "press" }));
    await eventually(() => this.nativeEvents(), (events) => events.filter((event) => event.kind === "capture-ready").length > ready, "actual native capture ready");
    // Capture several real ScriptProcessor buffers before ending the PTT gesture.
    await new Promise((done) => setTimeout(done, 500));
    await pet.evaluate(() => window.miraDesktop.surface.postToBackground({ kind: "voice.gesture", gesture: "release" }));
  }
  async stop(pet: Page) { await pet.evaluate(() => window.miraDesktop.surface.postToBackground({ kind: "voice.stop" })); }
}

/** Replace only physical microphone input; actual capture, resampling, IPC and WAV encoding run. */
export async function installGeneratedMicrophone(page: Page) {
  // Keep the hardware substitute self-contained: tsx's function-name helper is not present in Chromium.
  await page.evaluate(`(() => {
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", { configurable: true, value: async () => {
      const context = new AudioContext(), oscillator = context.createOscillator(), destination = context.createMediaStreamDestination();
      oscillator.frequency.value = 440; oscillator.connect(destination); oscillator.start(); await context.resume();
      for (const track of destination.stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { stop(); oscillator.stop(); void context.close(); };
      }
      return destination.stream;
    } });
  })()`);
}

/** Observe actual playback commands, without replacing the native player or its acknowledgements. */
export async function playbackCommands(page: Page) {
  await page.evaluate(() => {
    const commands: unknown[] = []; Reflect.set(window, "speechPlayback", commands);
    window.miraDesktop.onVoicePlaybackCommand((command) => commands.push(command));
  });
  return async () => {
    const commands: unknown = await page.evaluate(() => Reflect.get(window, "speechPlayback"));
    assert.ok(Array.isArray(commands)); return commands.map(record);
  };
}
