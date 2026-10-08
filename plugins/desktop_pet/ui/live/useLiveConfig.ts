import { usePrivateAutosave, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { LiveConfig } from "./liveContracts";

/**
 * The role's live settings (#724), autosaved to the pet's private storage.
 * `live.config.set` merges the given fields, so the whole document is sent
 * and stored back as the backend normalised it. A new role (null id) has no
 * settings: nothing loads or saves until it exists.
 */
export function useLiveConfig(client: PluginRpcClient, roleId: string | null) {
  return usePrivateAutosave<LiveConfig>(client, roleId, {
    load: () => client.call<LiveConfig>("live.config.get", { role_id: roleId }),
    save: (config) => client.call<LiveConfig>("live.config.set", { ...config, role_id: roleId }),
  });
}

/** What the live settings fields read from and write through. */
export type LiveConfigAutosave = ReturnType<typeof useLiveConfig>;
