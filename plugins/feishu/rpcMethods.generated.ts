// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "account.resolve": "account.resolve",
  "account.send": "account.send",
  "account.targets": "account.targets",
  "accounts.disconnect": "accounts.disconnect",
  "accounts.profile": "accounts.profile",
  "accounts.save": "accounts.save",
  "accounts.send": "accounts.send",
  "accounts.verify": "accounts.verify",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
