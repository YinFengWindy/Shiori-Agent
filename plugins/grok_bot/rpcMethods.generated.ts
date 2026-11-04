// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "account.detail": "account.detail",
  "account.disconnect": "account.disconnect",
  "account.resolve": "account.resolve",
  "account.save": "account.save",
  "account.send": "account.send",
  "account.targets": "account.targets",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
