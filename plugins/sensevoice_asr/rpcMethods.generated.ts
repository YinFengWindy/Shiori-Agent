// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.
/** Backend method names owned by this plugin. */
export const rpcMethods = {
  "health": "health",
  "runtime.cancel": "runtime.cancel",
  "runtime.prepare": "runtime.prepare",
  "runtime.relocate": "runtime.relocate",
  "runtime.remove": "runtime.remove",
  "runtime.start": "runtime.start",
  "runtime.status": "runtime.status",
  "runtime.stop": "runtime.stop",
  "settings.get": "settings.get",
  "settings.set": "settings.set",
  "transcribe_file": "transcribe_file",
} as const;

/** A backend method accepted by this plugin. */
export type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];
