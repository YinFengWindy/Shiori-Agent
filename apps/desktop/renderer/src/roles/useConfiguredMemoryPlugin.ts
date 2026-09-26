import { useEffect, useState } from "react";
import { errorMessage } from "../shared/feedback/feedbackStore";

type Selection = { status: "loading" | "ready" | "error"; pluginId: string; error: string };

/** Maps the saved memory engine to the plugin that owns its Dashboard. */
export function memoryPluginId(engine: string): string {
  const normalized = engine.trim();
  return !normalized || normalized === "default" ? "default_memory" : normalized;
}

/** Tracks the saved engine across runtime configuration changes. */
export function useConfiguredMemoryPlugin(bridgeReady: boolean): Selection {
  const [selection, setSelection] = useState<Selection>({ status: "loading", pluginId: "", error: "" });

  useEffect(() => {
    if (!bridgeReady) return;
    let cancelled = false;
    let request = 0;
    setSelection((previous) => previous.status === "loading" ? previous : { status: "loading", pluginId: "", error: "" });
    const read = () => {
      const current = ++request;
      void window.miraDesktop.readSettings().then((snapshot) => {
        if (!cancelled && current === request) {
          const pluginId = memoryPluginId(snapshot.formData.memory.engine);
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
    read();
    const unsubscribe = window.miraDesktop.onEvent((event) => {
      if (event.method === "runtime.applied") read();
    });
    return () => { cancelled = true; unsubscribe(); };
  }, [bridgeReady]);

  return selection;
}
