import type { PluginSummary } from "./pluginBridgeClient";
import { activePluginIds as activePluginIdsShared } from "../../../src/plugins/activePluginIds";

/**
 * Admits renderer contributions only for unique, enabled, active backend IDs.
 *
 * Delegates to the shared implementation in `apps/desktop/src` (#262), which
 * the main process's surface-teardown diff also needs — both sides must
 * agree on exactly the same "which plugin ids does this roster admit"
 * answer, including the duplicate-id CONFLICT rule.
 */
export function activePluginIds(plugins: Pick<PluginSummary, "id" | "enabled" | "state">[]) {
  return activePluginIdsShared(plugins);
}
