import { errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { mergeContextStatus, type ChatContextStatus } from "./chatContextState";

type Snapshot = { status: ChatContextStatus | null; notice: string };
type Scope = { roleId: string; sessionKey: string };
type Entry = Scope & { snapshot: Snapshot; fresh: boolean; owner: symbol; pending?: Promise<void> };
const emptySnapshot: Snapshot = { status: null, notice: "" };
const pendingModelSnapshot: Snapshot = { status: null, notice: "正在切换模型" };
const scopeKey = (roleId: string, sessionKey: string) => JSON.stringify([roleId, sessionKey]);

/** Instance-local context reads, deduplicated and guarded against invalidated responses. */
export class ChatContextCache {
  private entries = new Map<string, Entry>();
  private listeners = new Set<() => void>();
  private pendingModels = new Set<string>();

  /** Subscribe to stable per-session snapshots. */
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private emit() { for (const listener of this.listeners) listener(); }
  private entry(roleId: string, sessionKey: string) {
    const key = scopeKey(roleId, sessionKey);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = { roleId, sessionKey, snapshot: emptySnapshot, fresh: false, owner: Symbol() };
      this.entries.set(key, entry);
    }
    return entry;
  }
  /** Get a cached snapshot without creating state during a React render. */
  get(roleId: string, sessionKey: string) {
    if (this.pendingModels.has(roleId)) return pendingModelSnapshot;
    return this.entries.get(scopeKey(roleId, sessionKey))?.snapshot ?? emptySnapshot;
  }
  /** Keep transient command feedback with the same session as its usage. */
  setNotice(roleId: string, sessionKey: string, notice: string) {
    const entry = this.entry(roleId, sessionKey);
    if (entry.snapshot.notice === notice) return;
    entry.snapshot = { ...entry.snapshot, notice };
    this.emit();
  }
  /** Mark matching scopes stale; configuration changes also discard displayed usage. */
  invalidate(scope: Partial<Scope> = {}, clear = false) {
    for (const entry of this.entries.values()) {
      if (scope.roleId !== undefined && scope.roleId !== entry.roleId) continue;
      if (scope.sessionKey !== undefined && scope.sessionKey !== entry.sessionKey) continue;
      entry.owner = Symbol();
      entry.pending = undefined;
      entry.fresh = false;
      if (clear) entry.snapshot = emptySnapshot;
    }
    this.emit();
  }
  /** Prevent reads of a model binding while its save is still pending. */
  setModelPending(roleId: string, pending: boolean) {
    if (pending) this.pendingModels.add(roleId);
    else this.pendingModels.delete(roleId);
    this.invalidate({ roleId }, true);
  }
  /** Begin a write whose result is accepted only within this cache generation. */
  beginUpdate(roleId: string, sessionKey: string) {
    this.invalidate({ roleId, sessionKey });
    const entry = this.entry(roleId, sessionKey);
    const owner = entry.owner;
    const current = () => this.entries.get(scopeKey(roleId, sessionKey)) === entry && entry.owner === owner;
    return {
      current,
      accept: (next: ChatContextStatus) => {
        if (!current() || next.session_key !== sessionKey) return;
        entry.snapshot = { status: mergeContextStatus(entry.snapshot.status, next), notice: "" };
        // Busy and unavailable budgets must be retried on activation or completion.
        entry.fresh = !next.busy && next.tokens !== null && next.model_context_window !== null;
        this.emit();
      },
    };
  }
  /** Reuse complete results and in-flight reads; failures remain retryable. */
  async read(roleId: string, sessionKey: string) {
    if (!roleId || !sessionKey || this.pendingModels.has(roleId)) return;
    const entry = this.entry(roleId, sessionKey);
    if (entry.fresh) return;
    if (entry.pending) return entry.pending;
    const update = this.beginUpdate(roleId, sessionKey);
    this.setNotice(roleId, sessionKey, "");
    entry.pending = (async () => {
      try {
        update.accept(await invokeBridgePayload<ChatContextStatus>(window.miraDesktop.invoke, "chat.context.status", { role_id: roleId }));
      } catch (error) {
        if (update.current()) {
          entry.snapshot = { status: null, notice: errorFeedback(error, "上下文用量暂不可用，请稍后重试").message };
          this.emit();
        }
      } finally {
        if (update.current()) entry.pending = undefined;
      }
    })();
    return entry.pending;
  }
  /** Retry an early busy read once after its owning desktop turn has finished. */
  async finishTurn(roleId: string, sessionKey: string) {
    const pending = this.read(roleId, sessionKey);
    const entry = this.entry(roleId, sessionKey);
    const owner = entry.owner;
    await pending;
    if (this.entries.get(scopeKey(roleId, sessionKey)) === entry && entry.owner === owner && entry.snapshot.status?.busy) {
      await this.read(roleId, sessionKey);
    }
  }
  /** Revoke all outstanding responses when the owning composer unmounts. */
  clear() {
    this.entries.clear();
    this.pendingModels.clear();
  }
}
