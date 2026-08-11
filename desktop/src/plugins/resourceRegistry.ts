import { isAbsolute, resolve } from "node:path";

export const pluginResourceScheme = "shiori-plugin";

/** Tracks package roots that the main process has accepted from installed records. */
export class PluginResourceRegistry {
  private readonly roots = new Map<string, string>();

  replace(entries: Iterable<{ pluginId: string; packageDir: string }>): void {
    const next = new Map<string, string>();
    for (const entry of entries) {
      if (isAbsolute(entry.packageDir)) {
        next.set(entry.pluginId, resolve(entry.packageDir));
      }
    }
    this.roots.clear();
    for (const [pluginId, packageDir] of next) this.roots.set(pluginId, packageDir);
  }

  packageRoot(pluginId: string): string | null {
    return this.roots.get(pluginId) ?? null;
  }

  entryUrl(pluginId: string, entrypoint: string): string {
    return `${pluginResourceScheme}://${pluginId}/${entrypoint.split("/").map(encodeURIComponent).join("/")}`;
  }
}
