import type { PluginRpcClient } from "../plugins/pluginBridgeClient";
import type { RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { semanticListParams, type RoleSemanticDetail, type RoleSemanticList, type RoleSemanticQuery } from "./roleSemanticMemory";

/** The configured memory plugin's namespace-scoped RPC client; reads only need `call`. */
export type MemoryRpc = Pick<PluginRpcClient, "call">;

const clientKeys = new WeakMap<MemoryRpc, number>();
let nextClientKey = 0;

/** Stable per-client token, so a replaced client (new runtime generation) re-reads everything. */
export function memoryClientKey(client: MemoryRpc) {
  let key = clientKeys.get(client);
  if (key === undefined) {
    key = ++nextClientKey;
    clientKeys.set(client, key);
  }
  return key;
}

function requireRole<T extends { role_id: string }>(roleId: string, response: T) {
  if (response.role_id !== roleId) throw new Error("角色不匹配");
  return response;
}

/** Reads the role's five Markdown documents through `roles.memory.documents`. */
export async function readMemoryDocuments(client: MemoryRpc, roleId: string) {
  return requireRole(roleId, await client.call<RoleMemoryDocumentsPayload>("roles.memory.documents", { role_id: roleId }));
}

/** Reads one batch of the role's semantic items through `roles.memory.semantic.list`. */
export async function readSemanticBatch(client: MemoryRpc, roleId: string, query: RoleSemanticQuery, page: number) {
  return requireRole(roleId, await client.call<RoleSemanticList>("roles.memory.semantic.list", semanticListParams(roleId, query, page)));
}

/** Reads one semantic item through `roles.memory.semantic.detail`; a different item is an error. */
export async function readSemanticDetail(client: MemoryRpc, roleId: string, itemId: string) {
  const response = requireRole(roleId, await client.call<RoleSemanticDetail>("roles.memory.semantic.detail", { role_id: roleId, item_id: itemId }));
  if (response.status === "ready" && response.item?.id !== itemId) throw new Error("记忆条目不匹配");
  return response;
}
