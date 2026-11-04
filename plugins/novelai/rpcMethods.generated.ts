// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "generate": "generate",
  "history": "history",
  "prompt_tags.delete": "prompt_tags.delete",
  "prompt_tags.list": "prompt_tags.list",
  "prompt_tags.upsert": "prompt_tags.upsert",
  "regenerateMessageMedia": "regenerateMessageMedia",
  "role_settings.get": "role_settings.get",
  "role_settings.set": "role_settings.set",
  "status": "status",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
