// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "chat_status": "chat_status",
  "history": "history",
  "stage_prompts_get": "stage_prompts_get",
  "stage_prompts_set": "stage_prompts_set",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
