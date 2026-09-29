import { useEffect } from "react";
import { usePluginHostServices } from "@shiori/plugin-sdk";

/** Refreshes the open Story gallery when its plugin publishes changed resources. */
export function useStoryGalleryRefresh(active: boolean, refresh: () => Promise<void>, reportError: (message: string) => void) {
  const host = usePluginHostServices();
  useEffect(() => {
    if (!active) return;
    return host.onEvent((event) => {
      if (event.method !== "plugin.story.resource.changed") return;
      void refresh().catch((error: unknown) => {
        reportError(error instanceof Error ? error.message : "无法刷新 CG 集");
      });
    });
  }, [active, host, refresh, reportError]);
}
