// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "roles.memory.documents": "roles.memory.documents",
  "roles.memory.semantic.detail": "roles.memory.semantic.detail",
  "roles.memory.semantic.list": "roles.memory.semantic.list",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
