import { usePrivateAutosave, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { RoleVoice } from "../shared/contracts";

/**
 * The role's private voice document, autosaved through this plugin's RPC.
 * A new role (null id) has no document: nothing loads or saves until it exists.
 */
export function useRoleVoice(client: PluginRpcClient, roleId: string | null) {
  return usePrivateAutosave<RoleVoice>(client, roleId, {
    load: () => client.call<RoleVoice>("role.get", { role_id: roleId }),
    save: (voice) => client.call<RoleVoice>("role.set", { role_id: roleId, voice }),
  });
}

/** What the voice editor reads from and writes through `useRoleVoice`. */
export type RoleVoiceAutosave = ReturnType<typeof useRoleVoice>;
