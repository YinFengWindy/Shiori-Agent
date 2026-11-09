// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "role.get": "role.get",
  "role.set": "role.set",
  "settings.get": "settings.get",
  "settings.set": "settings.set",
  "transcribe_file": "transcribe_file",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
