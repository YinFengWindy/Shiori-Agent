// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "cg.list": "cg.list",
  "cg.regenerate": "cg.regenerate",
  "cg.retry": "cg.retry",
  "continue": "continue",
  "create": "create",
  "delete": "delete",
  "get": "get",
  "input": "input",
  "list": "list",
  "rename": "rename",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
