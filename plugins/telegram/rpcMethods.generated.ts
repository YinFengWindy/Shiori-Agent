// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "account.resolve": "account.resolve",
  "account.send": "account.send",
  "account.targets": "account.targets",
  "bot.disconnect": "bot.disconnect",
  "bot.save": "bot.save",
  "identity.get": "identity.get",
  "known.list": "known.list",
  "member.get": "member.get",
  "target.send": "target.send",
  "token.verify": "token.verify",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
