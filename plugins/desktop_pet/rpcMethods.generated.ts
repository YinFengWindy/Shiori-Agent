// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "bilibili.account.logout": "bilibili.account.logout",
  "bilibili.account.status": "bilibili.account.status",
  "bilibili.login.poll": "bilibili.login.poll",
  "bilibili.login.start": "bilibili.login.start",
  "binding.get": "binding.get",
  "bubble.dismiss": "bubble.dismiss",
  "live.config.get": "live.config.get",
  "live.config.set": "live.config.set",
  "live.pause": "live.pause",
  "live.reply.outcome": "live.reply.outcome",
  "live.resume": "live.resume",
  "live.start": "live.start",
  "live.status": "live.status",
  "live.stop": "live.stop",
  "pets.import": "pets.import",
  "pets.list": "pets.list",
  "pets.remove": "pets.remove",
  "pets.select": "pets.select",
  "voice.context.get": "voice.context.get",
  "voice.preferences.get": "voice.preferences.get",
  "voice.preferences.set": "voice.preferences.set",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
