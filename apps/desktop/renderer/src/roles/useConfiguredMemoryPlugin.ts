import { useEffect, useState } from "react";

type Selection = { status: "loading" | "ready" | "error"; pluginId: string };

/** Maps the saved memory engine to the plugin that owns its Dashboard. */
export function memoryPluginId(engine: string): string {
  const normalized = engine.trim();
  return !normalized || normalized === "default" ? "default_memory" : normalized;
}

/** Tracks the saved engine across runtime configuration changes. */
export function useConfiguredMemoryPlugin(bridgeReady: boolean): Selection {
  const [selection, setSelection] = useState<Selection>({ status: "loading", pluginId: "" });

  useEffect(() => {
    if (!bridgeReady) return;
    let cancelled = false;
    let request = 0;
    const read = () => {
      const current = ++request;
      setSelection({ status: "loading", pluginId: "" });
      void window.miraDesktop.readSettings().then((snapshot) => {
        if (!cancelled && current === request) setSelection({ status: "ready", pluginId: memoryPluginId(snapshot.formData.memory.engine) });
      }).catch(() => {
        if (!cancelled && current === request) setSelection({ status: "error", pluginId: "" });
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
