/**
 * DOM primitives shared by every window that loads a runtime-admitted plugin
 * renderer entry (the main window's UI bootstrap, the plugin-host window's
 * background bootstrap, and a surface window's bootstrap). Each of those
 * windows is a separate Electron renderer process, so nothing here is a
 * singleton — it is the two DOM operations themselves that were duplicated,
 * not any state.
 */

/** Appends a `<link rel="stylesheet">` for a granted plugin CSS URL; resolves an undo function. */
export function loadRuntimePluginCss(url: string): Promise<() => void> {
  return new Promise((resolve, reject) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = url;
    link.onload = () => resolve(() => link.remove());
    link.onerror = () => { link.remove(); reject(new Error(`Plugin CSS could not be loaded: ${url}`)); };
    document.head.append(link);
  });
}

/** Dynamically imports a granted plugin ESM entry (a `shiori-plugin://` URL). */
export function importRuntimePluginModule(url: string): Promise<{ default: unknown }> {
  return import(/* @vite-ignore */ url);
}
