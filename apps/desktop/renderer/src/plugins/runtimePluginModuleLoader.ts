import type { RuntimePluginUi } from "../../../src/plugins/uiContract";

/**
 * Loader boundaries shared by every runtime-admitted plugin renderer entry
 * (`ui`, `background`, `surface`): module evaluation, CSS loading and
 * cleanup, ABI validation and registry mutation are all supplied by the
 * caller so each entry point can plug in its own contract and registry while
 * sharing the exact same load order and failure handling.
 */
export type RuntimePluginModuleLoadHost<TModule> = {
  importModule: (url: string) => Promise<{ default: unknown }>;
  loadCss: (url: string) => Promise<() => void>;
  /** Rejects a malformed contribution before `register` ever sees it. */
  validate: (value: unknown, pluginId: string) => asserts value is TModule;
  register: (module: TModule) => void;
  unregister: (pluginId: string) => void;
  /**
   * Called once, immediately after a contribution registers successfully.
   * Optional and additive — existing hosts that only care about failure
   * (logging/diagnostics) are unaffected. The backend activation report
   * (#262) is the only current consumer.
   */
  succeeded?: (pluginId: string) => void;
  failed: (pluginId: string, error: unknown) => void;
};

/**
 * Loads each admitted entry independently and removes its partial
 * contribution on failure.
 *
 * Extracted from the `ui`-only `loadRuntimePluginUi` so `background` and
 * `surface` runtime loading go through the identical sequence — CSS first,
 * then the module, then ABI validation, then registration — rather than a
 * second hand-rolled copy of the same steps. `runtimePluginUi.ts` is a thin
 * wrapper over this that fixes `validate` to the UI ABI, so its own exported
 * behaviour (including exactly which cleanup runs in which order on a
 * partial failure) is unchanged.
 */
export async function loadRuntimePluginModules<TModule>(
  entries: RuntimePluginUi[],
  host: RuntimePluginModuleLoadHost<TModule>,
) {
  const dispose: (() => void)[] = [];
  for (const entry of entries) {
    const styles: (() => void)[] = [];
    try {
      if (entry.error) throw new Error(entry.error);
      for (const css of entry.css) styles.push(await host.loadCss(css));
      const { default: module } = await host.importModule(entry.entry);
      host.validate(module, entry.pluginId);
      host.register(module);
      host.succeeded?.(entry.pluginId);
      dispose.push(() => { host.unregister(entry.pluginId); for (const remove of styles) remove(); });
    } catch (error) {
      host.unregister(entry.pluginId);
      for (const remove of styles) remove();
      host.failed(entry.pluginId, error);
    }
  }
  return () => { for (const remove of dispose) remove(); };
}
