import { usePrivateAutosave, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { rpcMethods } from "../rpcMethods.generated";
import type { RoleVoice } from "../shared/contracts";

/** Persist only this role's Fish mapping, outside the role's primary document. */
export function useRoleVoice(client: PluginRpcClient, roleId: string | null) {
  return usePrivateAutosave<RoleVoice>(client, roleId, {
    load: () => client.call<RoleVoice>(rpcMethods["role.get"], { role_id: roleId }),
    save: (voice) => client.call<RoleVoice>(rpcMethods["role.set"], { role_id: roleId, voice }),
  });
}
