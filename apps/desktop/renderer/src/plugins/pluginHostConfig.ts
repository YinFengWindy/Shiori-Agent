import type { PluginConfigValues, PluginHostConfig } from "@yinfengwindy/shiori-sdk";
import { createPluginBridgeClient, type PluginBridgeClient } from "./pluginBridgeClient";
import { pluginConfigChanges, type PluginConfigChanges } from "./pluginConfigChanges";

/**
 * `host.config` bound to one plugin (#505): reads and saves only that
 * plugin's `[plugins.<id>]` table through `plugin.config.get` / `set`, the
 * same bridge methods as its page in 设置 › 插件, and publishes each stored
 * result so that page refreshes.
 */
export function createPluginHostConfig(
  pluginId: string,
  client: Pick<PluginBridgeClient, "getConfig" | "setConfig"> = createPluginBridgeClient(),
  changes: PluginConfigChanges = pluginConfigChanges,
): PluginHostConfig {
  let previous: Promise<PluginConfigValues | undefined> = Promise.resolve(undefined);
  const service: PluginHostConfig = {
    async get() {
      return (await client.getConfig(pluginId)).values;
    },
    save(patch) {
      // One save at a time, each merged over what the previous one stored:
      // `plugin.config.set` replaces the whole table, so two saves merged over
      // the same read would drop one another's fields.
      const saved = previous.then(async () => {
        const current = await client.getConfig(pluginId);
        const result = await client.setConfig(pluginId, { ...current.values, ...patch }, { operationId: crypto.randomUUID() });
        changes.publish(pluginId, result.values, service);
        return result.values;
      });
      // The caller gets the failure through `saved`; the queue only waits for it.
      previous = saved.catch(() => undefined);
      return saved;
    },
    subscribe(listener) {
      return changes.subscribe(pluginId, (values) => listener(values));
    },
  };
  return service;
}
