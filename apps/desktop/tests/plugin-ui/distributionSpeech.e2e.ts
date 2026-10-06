import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { SpeechApp, playbackCommands } from "./distributionSpeechApp";
import { speechAssets, speechConfiguration } from "./distributionSpeechFixtures";
import { SpeechServer } from "./distributionSpeechServer";
import { prepareSpeech } from "./distributionSpeechSetup";
import { eventually } from "./packagedApp";
import { Evidence, record } from "./packagedEvidence";

const repository = resolve(import.meta.dirname, "../../../..");
await mkdir(resolve(repository, ".test-tmp-root"), { recursive: true });
const output = await mkdtemp(resolve(repository, ".test-tmp-root/distribution-speech-"));
const workspace = resolve(output, "workspace"), profile = resolve(output, "profile");
await mkdir(workspace); await mkdir(profile);
const server = new SpeechServer(), url = await server.start();
await writeFile(resolve(workspace, "config.toml"), speechConfiguration(url), "utf8");
const executable = process.env.SHIORI_E2E_ELECTRON_PATH ?? resolve(repository, "apps/desktop/node_modules/electron/dist", process.platform === "win32" ? "electron.exe" : "electron");
const app = new SpeechApp({ workspace, profile, executable }, new Evidence(output), "development");
const started = async () => (await app.nativeEvents()).filter((event) => event.kind === "playback-started");
const completed = async () => (await app.chatEvents()).filter((event) => event.method === "chat.done");
try {
  const pet = await prepareSpeech(app, repository, output, url, await speechAssets(repository, output));
  await app.speak(pet);
  await eventually(completed, (events) => events.length === 1, "first real chat turn committed");
  const first = await eventually(started, (events) => events.length === 1, "real native playback started");
  const sender = first[0].sender;
  const playback = (await Promise.all(app.app!.windows().map(async (page) => ({ page, sender: await (await app.app!.browserWindow(page)).evaluate((window) => window.webContents.id) })))).find((window) => window.sender === sender)?.page;
  assert.ok(playback); const commands = await playbackCommands(playback);
  await app.stop(pet);
  await eventually(commands, (items) => items.some((command) => command.command === "cancel"), "manual stop reached actual player");
  assert.equal(server.count("/tts"), 1);
  await app.evidence.add("real-chat-to-native-playback-and-stop", { requests: server.requests, native: await app.nativeEvents(), commands: await commands() });

  await app.speak(pet);
  await eventually(async () => server.count("/tts"), (count) => count === 2, "second synthesis held by HTTP barrier");
  await eventually(completed, (events) => events.length === 2, "second real chat turn committed");
  await app.stop(pet);
  await app.speak(pet);
  await eventually(completed, (events) => events.length === 3, "new turn committed while old inference remains held");
  assert.equal(server.count("/v1/audio/transcriptions"), 3);
  assert.equal(server.count("/tts"), 2, "new synthesis bypassed actual in-flight inference");
  assert.equal((await started()).length, 1, "cancelled synthesis started playback before release");
  server.release();
  await eventually(async () => server.count("/tts"), (count) => count === 3, "new synthesis starts after old response finishes");
  await eventually(started, (events) => events.length === 2, "only new turn starts playback");
  const played = (await commands()).filter((command) => command.command === "play");
  assert.equal(played.length, 1, "late old result was played");
  assert.equal((await started())[1].value, played[0].id, "new response was not acknowledged by the actual player");
  assert.equal(played[0].audioBase64, server.audioResponses.find((response) => response.index === 3)?.audioBase64, "player received the cancelled turn instead of the new response");
  assert.ok(!played.some((command) => command.audioBase64 === server.audioResponses.find((response) => response.index === 2)?.audioBase64), "cancelled response reached native playback");
  assert.deepEqual(server.requests.filter((request) => request.path === "/tts").map((request) => request.body.text), ["这是第1轮回复。", "这是第2轮回复。", "这是第3轮回复。"]);
  await app.stop(pet);

  const events = await app.chatEvents();
  assert.deepEqual(events.filter((event) => event.method === "chat.error"), []);
  for (const done of await completed()) {
    const payload = record(done.payload);
    assert.equal(payload.role_id, "speech-fixture");
    assert.ok(events.some((event) => event.method === "chat.delta" && record(event.payload).turn_id === payload.turn_id && record(event.payload).session_key === payload.session_key));
  }
  const history = await app.call("session.messagesPage", { role_id: "speech-fixture", limit: 50 });
  const messages = record(history.page).messages; assert.ok(Array.isArray(messages));
  for (let turn = 1; turn <= 3; turn++) assert.ok(messages.some((message) => record(message).role === "user" && record(message).content === `语音组合测试第${turn}轮`));
  assert.equal(messages.filter((message) => record(message).role === "assistant").length, 3);
  assert.deepEqual(server.failures, []); assert.deepEqual(app.errors, []);
  assert.deepEqual((await app.nativeEvents()).filter((event) => String(event.kind).endsWith("error")), []);
  await app.screenshot("desktop-pet-composed-speech", pet);
  const responseAudio = server.audioResponses.map(({ index, audioBase64, at }) => ({ index, at, sha256: createHash("sha256").update(Buffer.from(audioBase64, "base64")).digest("hex") }));
  await app.evidence.add("cancelled-result-discarded-and-new-turn-serialized", { requests: server.requests, responseAudio, events, history, native: await app.nativeEvents(), commands: await commands() });
  await app.evidence.add("complete", { realModel: false, realLlm: false, realMicrophone: false, frozenRuntime: false, desktopPetEnabled: true, actualPluginZipInstall: true, actualNativeCaptureAndPlayback: true, input: "generated WebAudio MediaStream", services: "loopback HTTP protocol doubles; real ASR/TTS plugin implementations and chat dispatcher", errors: app.errors });
} catch (error) {
  if (app.page) { await writeFile(resolve(output, "failure-dom.txt"), await app.page.locator("body").innerText(), "utf8"); await app.screenshot("failure"); }
  await writeFile(resolve(output, "failure.txt"), error instanceof Error ? error.stack ?? error.message : String(error), "utf8");
  throw error;
} finally {
  server.release(); await app.close(); await server.close();
  await writeFile(resolve(output, "http-requests.json"), JSON.stringify(server.requests, null, 2), "utf8");
  await writeFile(resolve(output, "process-stderr.log"), app.processErrors.join(""), "utf8");
  console.log(`Speech integration evidence: ${output}`);
}
