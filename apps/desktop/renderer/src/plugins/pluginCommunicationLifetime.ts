import { PluginBridgeError } from "./pluginBridgeError";

/** Rejects pending client requests immediately when their owning context leaves. */
export class PluginCommunicationLifetime {
  private readonly abort = new AbortController();

  /** Prevents old contexts from starting new work after disposal or replacement. */
  assertActive() {
    if (this.abort.signal.aborted) throw new PluginBridgeError("插件通信已处置", "plugin_unavailable");
  }

  /** Ends local waits; backend cleanup independently cancels renderer rendezvous. */
  dispose() { this.abort.abort(); }

  /** Races one transport operation against owner disposal without leaking listeners. */
  async wait<T>(operation: Promise<T>): Promise<T> {
    this.assertActive();
    let rejectDisposed: () => void = () => {};
    const disposed = new Promise<never>((_resolve, reject) => {
      rejectDisposed = () => reject(new PluginBridgeError("插件通信已处置", "plugin_unavailable"));
      this.abort.signal.addEventListener("abort", rejectDisposed, { once: true });
    });
    try { return await Promise.race([operation, disposed]); }
    finally { this.abort.signal.removeEventListener("abort", rejectDisposed); }
  }
}
