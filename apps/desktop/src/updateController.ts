import type { EventEmitter } from "node:events";
import type { AppUpdater, UpdateInfo, ProgressInfo } from "electron-updater";
import type { DesktopUpdateState } from "./updateContract.js";

type UpdateEngine = Pick<AppUpdater, "autoDownload" | "checkForUpdates" | "quitAndInstall">
  & Pick<EventEmitter, "on" | "removeListener">;

/** Owns one update lifecycle, including concurrent checks and renderer snapshots. */
export class DesktopUpdateController {
  private state: DesktopUpdateState;
  private checking: Promise<DesktopUpdateState> | null = null;
  private readonly listeners: Array<Parameters<EventEmitter["on"]>> = [];

  constructor(private readonly options: {
    version: string;
    engine: UpdateEngine | null;
    publish: (state: DesktopUpdateState) => void;
    onError: (error: unknown) => void;
  }) {
    this.state = {
      revision: 0, currentVersion: options.version,
      phase: options.engine ? "idle" : "unsupported",
      latestVersion: null, progress: 0, error: null,
    };
    if (!options.engine) return;
    options.engine.autoDownload = true;
    this.listen("checking-for-update", () => this.update({ phase: "checking", error: null }));
    this.listen("update-not-available", () => this.markCurrent());
    this.listen("update-available", (info: UpdateInfo) => this.update({
      phase: "downloading", latestVersion: info.version, progress: 0,
    }));
    this.listen("download-progress", (info: ProgressInfo) => this.update({
      phase: "downloading", progress: Math.max(0, Math.min(100, info.percent)),
    }));
    this.listen("update-downloaded", (info: UpdateInfo) => this.update({
      phase: "downloaded", latestVersion: info.version, progress: 100, error: null,
    }));
    this.listen("error", (error: Error) => {
      // The engine emits before rejecting its check; let check() finish an empty channel normally.
      if (!this.isEmptyReleaseCheck(error)) this.recordError(error);
    });
  }

  /** Returns the most recent immutable status snapshot. */
  getState() { return this.state; }

  /** Checks once and preserves an in-flight download or ready installer. */
  check(): Promise<DesktopUpdateState> {
    const engine = this.options.engine;
    if (!engine) return Promise.reject(new Error("开发模式不支持应用更新"));
    if (this.checking) return this.checking;
    if (["downloading", "downloaded", "installing"].includes(this.state.phase)) return Promise.resolve(this.state);
    this.update({ phase: "checking", error: null, progress: 0 });
    this.checking = Promise.resolve().then(() => engine.checkForUpdates()).then((result) => {
      if (!result) throw new Error("当前环境无法检查应用更新");
      void result.downloadPromise?.catch((error: unknown) => this.recordError(error));
      return this.state;
    }).catch((error: unknown) => {
      if (this.isEmptyReleaseCheck(error)) {
        this.markCurrent();
        return this.state;
      }
      this.recordError(error);
      throw error;
    }).finally(() => { this.checking = null; });
    return this.checking;
  }

  /** Installs only a completely downloaded update and relaunches the application. */
  install() {
    if (!this.options.engine || this.state.phase !== "downloaded") throw new Error("更新尚未下载完成");
    this.update({ phase: "installing", error: null });
    try {
      this.options.engine.quitAndInstall(false, true);
    } catch (error) {
      this.recordError(error);
      throw error;
    }
  }

  /** Releases the engine listeners owned by this controller. */
  dispose() {
    for (const [event, listener] of this.listeners) this.options.engine?.removeListener(event, listener);
    this.listeners.length = 0;
  }

  private listen(event: string, listener: Parameters<EventEmitter["on"]>[1]) {
    this.options.engine?.on(event, listener);
    this.listeners.push([event, listener]);
  }

  private update(patch: Partial<DesktopUpdateState>) {
    this.state = { ...this.state, ...patch, revision: this.state.revision + 1 };
    this.options.publish(this.state);
  }

  private markCurrent() {
    this.update({ phase: "current", latestVersion: null, progress: 0, error: null });
  }

  private isEmptyReleaseCheck(error: unknown) {
    return this.state.phase === "checking"
      && typeof error === "object" && error !== null && "code" in error
      && error.code === "ERR_UPDATER_NO_PUBLISHED_VERSIONS";
  }

  private recordError(error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    if (this.state.phase === "error" && this.state.error === message) return;
    this.update({ phase: "error", error: message });
    this.options.onError(error);
  }
}
