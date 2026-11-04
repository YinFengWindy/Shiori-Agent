// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "operations.cancel": "operations.cancel",
  "servers.delete": "servers.delete",
  "servers.list": "servers.list",
  "servers.login": "servers.login",
  "servers.logout": "servers.logout",
  "servers.reconnect": "servers.reconnect",
  "servers.refresh": "servers.refresh",
  "servers.save": "servers.save",
  "servers.set_enabled": "servers.set_enabled",
  "servers.test": "servers.test",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
