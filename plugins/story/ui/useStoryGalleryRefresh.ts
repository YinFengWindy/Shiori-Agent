import { useEffect } from "react";
import { usePluginHostServices } from "@shiori/sdk";

/** Refreshes the open Story gallery when its plugin publishes changed resources. */
export function useStoryGalleryRefresh(active: boolean, refresh: () => Promise<void>, reportError: (cause: unknown, summary?: string) => void) {
  const host = usePluginHostServices();
  useEffect(() => {
    if (!active) return;
    return host.onEvent((event) => {
      if (event.method !== "plugin.story.resource.changed") return;
      void refresh().catch((error: unknown) => {
        reportError(error, "CG 集刷新失败，请重试");
      });
    });
  }, [active, host, refresh, reportError]);
}
