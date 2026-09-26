import { useEffect, useState } from "react";
import { errorMessage } from "../shared/feedback/feedbackStore";

type Selection = { status: "loading" | "ready" | "error"; pluginId: string; error: string };
const settingsReadTimeoutMs = 15_000;

/** Maps the saved memory engine to the plugin that owns its Dashboard. */
export function memoryPluginId(engine: string): string {
  const normalized = engine.trim();
  return !normalized || normalized === "default" ? "default_memory" : normalized;
}

/** Bounds a settings read so a stalled bridge cannot retain an unresolved selection. */
export async function readMemoryPluginId(
  readSettings: typeof window.miraDesktop.readSettings,
  timeoutMs = settingsReadTimeoutMs,
): Promise<string> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const snapshot = await Promise.race([
      readSettings(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("设置读取超时")), timeoutMs);
      }),
    ]);
    return memoryPluginId(snapshot.formData.memory.engine);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

/** Tracks the saved engine across runtime configuration changes. */
export function useConfiguredMemoryPlugin(bridgeReady: boolean): Selection {
  const [selection, setSelection] = useState<Selection>({ status: "loading", pluginId: "", error: "" });

  useEffect(() => {
    if (!bridgeReady) return;
    let cancelled = false;
    let request = 0;
    setSelection((previous) => previous.status === "loading" ? previous : { status: "loading", pluginId: "", error: "" });
    const read = (gatePrevious: boolean) => {
      const current = ++request;
      if (gatePrevious) {
        setSelection((previous) => previous.status === "loading" ? previous : { status: "loading", pluginId: "", error: "" });
      }
      void readMemoryPluginId(() => window.miraDesktop.readSettings()).then((pluginId) => {
        if (!cancelled && current === request) {
          setSelection((previous) => previous.status === "ready" && previous.pluginId === pluginId
            ? previous : { status: "ready", pluginId, error: "" });
        }
      }).catch((error: unknown) => {
        if (!cancelled && current === request) {
          const message = errorMessage(error);
          setSelection((previous) => previous.status === "error" && previous.error === message
            ? previous : { status: "error", pluginId: "", error: message });
        }
      });
    };
    read(false);
    const unsubscribe = window.miraDesktop.onEvent((event) => {
      if (event.method === "runtime.applied" && event.payload.changed !== false) read(true);
    });
    return () => { cancelled = true; unsubscribe(); };
  }, [bridgeReady]);

  return selection;
}
