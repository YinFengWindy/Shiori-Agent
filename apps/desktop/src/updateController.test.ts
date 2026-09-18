import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { UpdateCheckResult, UpdateInfo } from "electron-updater";
import type { DesktopUpdateState } from "./updateContract.js";
import { DesktopUpdateController } from "./updateController.js";

const info: UpdateInfo = { version: "0.3.0", files: [], path: "setup.exe", sha512: "hash", releaseDate: "2026-09-09" };
const result: UpdateCheckResult = { isUpdateAvailable: false, updateInfo: info, versionInfo: info };

class FakeUpdater extends EventEmitter {
  autoDownload = false;
  checks = 0;
  installs: boolean[][] = [];
  checkResult: () => Promise<UpdateCheckResult | null> = async () => {
    this.emit("update-not-available", info);
    return result;
  };
  checkForUpdates() { this.checks += 1; return this.checkResult(); }
  quitAndInstall(silent = false, relaunch = false) { this.installs.push([silent, relaunch]); }
}

function fixture(engine: FakeUpdater | null = new FakeUpdater(), version = "0.2.0") {
  const errors: unknown[] = [];
  const published: DesktopUpdateState[] = [];
  const controller = new DesktopUpdateController({ version, engine, publish: (state) => published.push(state), onError: (error) => errors.push(error) });
  return { controller, errors, published };
}

function noPublishedVersionsError() {
  return Object.assign(new Error("No published versions on GitHub"), { code: "ERR_UPDATER_NO_PUBLISHED_VERSIONS" });
}

test("development builds expose version without creating an update engine", async () => {
  const { controller } = fixture(null);
  assert.equal(controller.getState().currentVersion, "0.2.0");
  assert.equal(controller.getState().phase, "unsupported");
  await assert.rejects(controller.check(), /开发模式/);
  assert.throws(() => controller.install(), /尚未下载完成/);
});

test("startup and manual checks share one request and expose current status", async () => {
  const engine = new FakeUpdater();
  const { controller } = fixture(engine);
  const first = controller.check();
  assert.equal(controller.check(), first);
  await first;
  assert.equal(engine.checks, 1);
  assert.equal(engine.autoDownload, true);
  assert.equal(controller.getState().phase, "current");
});

test("download progress survives manual checks and installation requires a ready update", async () => {
  const engine = new FakeUpdater();
  const { controller } = fixture(engine);
  engine.emit("update-available", info);
  engine.emit("download-progress", { percent: 42.5 });
  assert.equal(controller.getState().progress, 42.5);
  assert.equal(controller.getState().latestVersion, "0.3.0");
  await controller.check();
  assert.equal(engine.checks, 0);
  assert.throws(() => controller.install(), /尚未下载完成/);
  engine.emit("update-downloaded", info);
  controller.install();
  assert.deepEqual(engine.installs, [[false, true]]);
  assert.equal(controller.getState().phase, "installing");
  assert.throws(() => controller.install(), /尚未下载完成/);
  controller.dispose();
  assert.equal(engine.listenerCount("download-progress"), 0);
});

test("failed checks publish an error once and can be retried", async () => {
  const engine = new FakeUpdater();
  const { controller, errors } = fixture(engine);
  engine.checkResult = async () => {
    const error = new Error("network unavailable");
    engine.emit("error", error);
    throw error;
  };
  await assert.rejects(controller.check(), /network unavailable/);
  assert.equal(controller.getState().error, "network unavailable");
  assert.equal(errors.length, 1);
  engine.checkResult = async () => { engine.emit("update-not-available", info); return result; };
  await controller.check();
  assert.equal(controller.getState().phase, "current");
  assert.equal(controller.getState().error, null);
});

for (const emitError of [true, false]) {
  test(`empty release channels resolve as current without reporting errors (${emitError ? "event and rejection" : "rejection only"})`, async () => {
    const engine = new FakeUpdater();
    const { controller, errors, published } = fixture(engine, "0.3.0-rc.1");
    engine.checkResult = async () => {
      const error = noPublishedVersionsError();
      if (emitError) engine.emit("error", error);
      throw error;
    };

    const startupCheck = controller.check();
    assert.equal(controller.check(), startupCheck);
    const state = await startupCheck;
    assert.deepEqual(state, {
      revision: state.revision, currentVersion: "0.3.0-rc.1", phase: "current",
      latestVersion: null, progress: 0, error: null,
    });
    assert.equal((await controller.check()).phase, "current");
    assert.equal(engine.checks, 2);
    assert.deepEqual(errors, []);
    assert.equal(published.some((snapshot) => snapshot.phase === "error" || snapshot.error !== null), false);

    engine.checkResult = async () => {
      engine.emit("update-available", info);
      return { ...result, isUpdateAvailable: true };
    };
    const update = await controller.check();
    assert.equal(engine.checks, 3);
    assert.equal(update.phase, "downloading");
    assert.equal(update.latestVersion, "0.3.0");
  });
}

test("an empty release channel clears state left by a failed download", async () => {
  const engine = new FakeUpdater();
  const { controller, errors } = fixture(engine);
  engine.emit("update-available", info);
  engine.emit("download-progress", { percent: 42.5 });
  engine.emit("error", new Error("download failed"));
  engine.checkResult = async () => { throw noPublishedVersionsError(); };
  const state = await controller.check();
  assert.equal(state.phase, "current");
  assert.equal(state.latestVersion, null);
  assert.equal(state.progress, 0);
  assert.equal(state.error, null);
  assert.equal(errors.length, 1);
});

for (const code of [undefined, "ECONNRESET", "ERR_UPDATER_CHANNEL_FILE_NOT_FOUND", "ERR_UPDATER_INVALID_UPDATE_INFO", "ERR_UPDATER_NO_FILES_PROVIDED"]) {
  test(`check failures still reject when the message matches but the code is ${code ?? "absent"}`, async () => {
    const engine = new FakeUpdater();
    const { controller, errors, published } = fixture(engine);
    const error = Object.assign(new Error("No published versions on GitHub"), { code });
    engine.checkResult = async () => {
      engine.emit("error", error);
      throw error;
    };
    await assert.rejects(controller.check(), (actual) => actual === error);
    assert.equal(controller.getState().phase, "error");
    assert.equal(controller.getState().error, error.message);
    assert.deepEqual(errors, [error]);
    assert.equal(published.filter((state) => state.phase === "error").length, 1);
  });
}

for (const phase of ["downloading", "installing"] as const) {
  test(`the empty-channel code remains an error when emitted while ${phase}`, () => {
    const engine = new FakeUpdater();
    const { controller, errors } = fixture(engine);
    engine.emit("update-available", info);
    if (phase === "installing") {
      engine.emit("update-downloaded", info);
      controller.install();
    }
    const error = noPublishedVersionsError();
    engine.emit("error", error);
    assert.equal(controller.getState().phase, "error");
    assert.deepEqual(errors, [error]);
  });
}

test("the empty-channel code remains a failure when installation throws", () => {
  const engine = new FakeUpdater();
  const { controller, errors } = fixture(engine);
  const error = noPublishedVersionsError();
  engine.emit("update-downloaded", info);
  engine.quitAndInstall = () => { throw error; };
  assert.throws(() => controller.install(), (actual) => actual === error);
  assert.equal(controller.getState().phase, "error");
  assert.deepEqual(errors, [error]);
});

test("asynchronous download failures are observable and do not become unhandled rejections", async () => {
  const engine = new FakeUpdater();
  const { controller } = fixture(engine);
  engine.checkResult = async () => {
    engine.emit("update-available", info);
    return { ...result, isUpdateAvailable: true, downloadPromise: Promise.reject(new Error("download failed")) };
  };
  await controller.check();
  assert.equal(controller.getState().phase, "error");
  assert.equal(controller.getState().error, "download failed");
});

test("the empty-channel code remains a failure when a download promise rejects", async () => {
  const engine = new FakeUpdater();
  const { controller, errors } = fixture(engine);
  const error = noPublishedVersionsError();
  engine.checkResult = async () => {
    engine.emit("update-available", info);
    return { ...result, isUpdateAvailable: true, downloadPromise: Promise.reject(error) };
  };
  await controller.check();
  assert.equal(controller.getState().phase, "error");
  assert.deepEqual(errors, [error]);
});
