import type { PluginSummary } from "./pluginBridgeClient";

const storageKey = "shiori.pluginTrustDismissals.v1";
type TrustRequest = { plugin: PluginSummary; enable: boolean; operationId: string };
type TrustSnapshot = { request: TrustRequest | null; busy: boolean; error: string; stale: boolean };
const empty: TrustSnapshot = { request: null, busy: false, error: "", stale: false };

/** The directory and exact bytes shown to the user form one trust decision. */
export function pluginTrustKey(plugin: PluginSummary) {
  return JSON.stringify([plugin.candidateId, plugin.trustFingerprint]);
}

/** One main-window queue shared by startup and explicit plugin settings actions. */
export class PluginTrustQueue {
  private snapshot: TrustSnapshot = empty;
  private readonly listeners = new Set<() => void>();
  private plugins: PluginSummary[] = [];
  private dismissed = new Set<string>();
  private session = "";
  private storage: Pick<Storage, "getItem" | "setItem"> | undefined;

  /** Stable reference for useSyncExternalStore until a queue decision changes. */
  getSnapshot = () => this.snapshot;
  /** Subscribe without owning or resetting the application-scoped decision queue. */
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };

  /** Restore dismissals only for this Electron lifetime, including renderer reloads. */
  initialize(session: string, storage: Pick<Storage, "getItem" | "setItem">) {
    if (this.session === session) return;
    this.session = session;
    this.storage = storage;
    const raw = storage.getItem(storageKey);
    const saved: unknown = raw ? JSON.parse(raw) : null;
    const values = saved && typeof saved === "object" && "session" in saved && saved.session === session
      && "dismissed" in saved && Array.isArray(saved.dismissed) ? saved.dismissed : [];
    this.dismissed = new Set(values.filter((value): value is string => typeof value === "string"));
    this.chooseNext();
  }

  /** Keep the displayed content fixed while authoritative roster refreshes arrive. */
  synchronize(plugins: PluginSummary[]) {
    this.plugins = plugins;
    const request = this.snapshot.request;
    if (request && !this.snapshot.busy) {
      const current = plugins.find((plugin) => plugin.candidateId === request.plugin.candidateId);
      if (current?.trusted && !current.canTrust && current.contentFingerprint === request.plugin.trustFingerprint) {
        this.update(empty);
      } else if (!current || pluginTrustKey(current) !== pluginTrustKey(request.plugin) || !current.canTrust) {
        if (!this.snapshot.stale) this.update({ ...this.snapshot, stale: true, error: "插件内容或状态已变化，请取消后重新确认。" });
      }
    }
    this.chooseNext();
  }

  /** Manual retry ignores a previous dismissal; enabling is a separate explicit intent. */
  request(plugin: PluginSummary, enable = false) {
    if (this.snapshot.busy || !plugin.canTrust || !plugin.trustFingerprint) return;
    this.update({ request: { plugin, enable, operationId: crypto.randomUUID() }, busy: false, error: "", stale: false });
  }

  /** Cancel only this candidate, retaining it for a later manual retry or app launch. */
  dismiss() {
    if (this.snapshot.busy) return;
    this.rememberCurrent();
    this.update(empty);
    this.chooseNext();
  }

  /** Claim one confirmation so double clicks cannot issue concurrent writes. */
  begin() {
    if (!this.snapshot.request || this.snapshot.busy || this.snapshot.stale) return null;
    this.update({ ...this.snapshot, busy: true, error: "" });
    return this.snapshot.request;
  }

  /** A failed/unknown result stays visible; retry uses the same operation identity. */
  fail(error: string) {
    this.update({ ...this.snapshot, busy: false, error });
    this.synchronize(this.plugins);
  }

  /** Finish after the host's fresh roster confirms the actual grant and activation state. */
  complete() {
    this.rememberCurrent();
    this.update(empty);
    this.chooseNext();
  }

  private rememberCurrent() {
    if (this.snapshot.request) this.dismissed.add(pluginTrustKey(this.snapshot.request.plugin));
    this.storage?.setItem(storageKey, JSON.stringify({ session: this.session, dismissed: [...this.dismissed] }));
  }

  private chooseNext() {
    if (!this.session || this.snapshot.request) return;
    const next = this.plugins.find((plugin) => plugin.enabled && plugin.canTrust && plugin.trustFingerprint
      && !this.dismissed.has(pluginTrustKey(plugin)));
    if (next) this.request(next);
  }

  private update(next: TrustSnapshot) {
    if (this.snapshot === next) return;
    this.snapshot = next;
    for (const listener of this.listeners) listener();
  }

  /** Test isolation; production lifetime is owned by the main renderer. */
  reset() {
    this.plugins = [];
    this.dismissed.clear();
    this.session = "";
    this.storage = undefined;
    this.update(empty);
  }
}

/** Shared main-renderer owner; startup and settings must not show competing dialogs. */
export const pluginTrustQueue = new PluginTrustQueue();
