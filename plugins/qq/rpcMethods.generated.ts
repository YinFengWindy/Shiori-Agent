// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "account.resolve": "account.resolve",
  "account.send": "account.send",
  "account.targets": "account.targets",
  "accounts.begin": "accounts.begin",
  "accounts.cancel": "accounts.cancel",
  "accounts.disconnect": "accounts.disconnect",
  "accounts.discover": "accounts.discover",
  "accounts.logout": "accounts.logout",
  "accounts.managed_status": "accounts.managed_status",
  "accounts.refresh_qrcode": "accounts.refresh_qrcode",
  "accounts.send": "accounts.send",
  "accounts.settings": "accounts.settings",
  "accounts.start": "accounts.start",
  "accounts.stop": "accounts.stop",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
