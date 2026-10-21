import { usePrivateAutosave, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** Private role settings returned by the NovelAI role settings RPC. */
export type AutoCgPromptSettings = { prompt_instructions: string };

/** Autosave CG model instructions independently of the role editor's switch draft. */
export function useAutoCgPromptSettings(client: PluginRpcClient, roleId: string | null) {
  return usePrivateAutosave<AutoCgPromptSettings>(client, roleId, {
    load: () => client.call<AutoCgPromptSettings>("role_settings.get", { role_id: roleId }),
    save: (settings) => client.call<AutoCgPromptSettings>("role_settings.set", { role_id: roleId, ...settings }),
  });
}
