// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "agents.get": "agents.get",
  "agents.keys": "agents.keys",
  "agents.list": "agents.list",
  "agents.prompt": "agents.prompt",
  "sessions.list": "sessions.list",
  "tasks.cancel": "tasks.cancel",
  "tasks.continue": "tasks.continue",
  "tasks.get": "tasks.get",
  "tasks.list": "tasks.list",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
