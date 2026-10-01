import type { PluginRpcClient } from "@shiori/sdk";
import type { RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { semanticListParams, type RoleSemanticDetail, type RoleSemanticList, type RoleSemanticQuery } from "./roleSemanticMemory";

/** The configured memory plugin's namespace-scoped RPC client; reads only need `call`. */
export type MemoryRpc = Pick<PluginRpcClient, "call">;

/** What every memory read depends on: whose memory, through which client, as of which refresh. */
export type MemoryReadContext = {
  client: MemoryRpc;
  roleId: string;
  /** The page's refresh counter. */
  refreshKey: number;
};

const clientKeys = new WeakMap<MemoryRpc, number>();
let nextClientKey = 0;

function clientKey(client: MemoryRpc) {
  let key = clientKeys.get(client);
  if (key === undefined) {
    key = ++nextClientKey;
    clientKeys.set(client, key);
  }
  return key;
}

/**
 * Read identity under one context. A replaced client (new runtime
 * generation), another role or a refresh always yields a new key.
 */
export function memoryReadKey({ client, roleId, refreshKey }: MemoryReadContext, ...parts: Array<string | number>) {
  return [clientKey(client), roleId, refreshKey, ...parts].join(":");
}

function requireRole<T extends { role_id: string }>(roleId: string, response: T) {
  if (response.role_id !== roleId) throw new Error("角色不匹配");
  return response;
}

/** Reads the role's five Markdown documents through `roles.memory.documents`. */
export async function readMemoryDocuments({ client, roleId }: MemoryReadContext) {
  return requireRole(roleId, await client.call<RoleMemoryDocumentsPayload>("roles.memory.documents", { role_id: roleId }));
}

/** Reads one batch of the role's semantic items through `roles.memory.semantic.list`. */
export async function readSemanticBatch({ client, roleId }: MemoryReadContext, query: RoleSemanticQuery, page: number) {
  return requireRole(roleId, await client.call<RoleSemanticList>("roles.memory.semantic.list", semanticListParams(roleId, query, page)));
}

/**
 * Reads one semantic item through `roles.memory.semantic.detail`. A null item
 * means it no longer exists; a different item is an error.
 */
export async function readSemanticDetail({ client, roleId }: MemoryReadContext, itemId: string) {
  const response = requireRole(roleId, await client.call<RoleSemanticDetail>("roles.memory.semantic.detail", { role_id: roleId, item_id: itemId }));
  if (response.item && response.item.id !== itemId) throw new Error("记忆条目不匹配");
  return response;
}
