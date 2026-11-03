import { PluginBridgeError } from "@yinfengwindy/shiori-sdk";

/** Why this exact communication owner stopped accepting results. */
export type PluginCommunicationEndReason = "context_disposed" | "plugin_disabled" | "plugin_reloading" | "bridge_exited" | "runtime_replaced";

const endMessages: Record<PluginCommunicationEndReason, string> = {
  context_disposed: "插件通信已处置",
  plugin_disabled: "插件已停用",
  plugin_reloading: "插件正在重载",
  bridge_exited: "插件桥接进程已退出",
  runtime_replaced: "插件运行代际已替换",
};

/** Rejects pending client requests immediately when their owning context leaves. */
export class PluginCommunicationLifetime {
  private readonly abort = new AbortController();

  /** Prevents old contexts from starting new work after disposal or replacement. */
  assertActive() {
    if (this.abort.signal.aborted) throw this.abort.signal.reason;
  }

  /** Ends local waits; backend cleanup independently cancels renderer rendezvous. */
  dispose(reason: PluginCommunicationEndReason = "context_disposed") {
    this.abort.abort(new PluginBridgeError(endMessages[reason], reason === "plugin_reloading" ? "plugin_reloading" : "plugin_unavailable", { reason }));
  }

  /** Races one transport operation against owner disposal without leaking listeners. */
  async wait<T>(operation: Promise<T>): Promise<T> {
    this.assertActive();
    let rejectDisposed: () => void = () => {};
    const disposed = new Promise<never>((_resolve, reject) => {
      rejectDisposed = () => reject(this.abort.signal.reason);
      this.abort.signal.addEventListener("abort", rejectDisposed, { once: true });
    });
    try { return await Promise.race([operation, disposed]); }
    finally { this.abort.signal.removeEventListener("abort", rejectDisposed); }
  }
}
