import { validateRuntimePluginUi } from "./runtimePluginUiValidation";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import type { PluginUiModule } from "./pluginUiModuleContract";

/** Loader boundaries keep module evaluation and CSS cleanup independently testable. */
export type RuntimePluginUiHost = {
  importModule: (url: string) => Promise<{ default: unknown }>;
  loadCss: (url: string) => Promise<() => void>;
  register: (module: PluginUiModule) => void;
  unregister: (pluginId: string) => void;
  failed: (pluginId: string, error: unknown) => void;
};

/** Loads each admitted plugin independently and removes its partial UI on failure. */
export async function loadRuntimePluginUi(entries: RuntimePluginUi[], host: RuntimePluginUiHost) {
  const dispose: (() => void)[] = [];
  for (const entry of entries) {
    const styles: (() => void)[] = [];
    try {
      if (entry.error) throw new Error(entry.error);
      for (const css of entry.css) styles.push(await host.loadCss(css));
      const { default: module } = await host.importModule(entry.entry);
      assertRuntimePluginUiModule(module, entry.pluginId);
      host.register(module);
      dispose.push(() => { host.unregister(entry.pluginId); for (const remove of styles) remove(); });
    } catch (error) {
      host.unregister(entry.pluginId);
      for (const remove of styles) remove();
      host.failed(entry.pluginId, error);
    }
  }
  return () => { for (const remove of dispose) remove(); };
}

/** Rejects malformed contributions before any registry mutation. */
export function assertRuntimePluginUiModule(value: unknown, pluginId: string): asserts value is PluginUiModule {
  validateRuntimePluginUi(value, pluginId);
}
