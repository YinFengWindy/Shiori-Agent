import { usePluginConfigController } from "../../../apps/desktop/renderer/src/plugins/usePluginConfigController";

/**
 * Fallbacks for the two configured model ids, used only until the plugin's
 * config has loaded; the configured value always wins once it has.
 */
const defaultModelFallback = "nai-diffusion-4-5-curated";
const nsfwModelFallback = "nai-diffusion-4-5-full";

/**
 * The prompt-level switches that are really plugin config (NSFW, quality
 * tags, undesired-content preset), read and autosaved through the same
 * controller as the plugin's settings tab, plus the model they resolve to.
 */
export function useNovelAiPromptSettings() {
  const config = usePluginConfigController("novelai");
  const draft = config.draft;
  const nsfwEnabled = Boolean(draft?.nsfw_enabled);
  const addQualityTags = Boolean(draft?.add_quality_tags);
  const undesiredContentPreset = Number(draft?.undesired_content_preset ?? 0);
  const configuredDefaultModel = typeof draft?.default_model === "string" ? draft.default_model : "";
  const configuredNsfwModel = typeof draft?.nsfw_model === "string" ? draft.nsfw_model : "";
  const model = nsfwEnabled
    ? (configuredNsfwModel || nsfwModelFallback)
    : (configuredDefaultModel || defaultModelFallback);

  return {
    nsfwEnabled,
    addQualityTags,
    undesiredContentPreset,
    model,
    setNsfwEnabled: (value: boolean) => config.updateDraft((current) => ({ ...current, nsfw_enabled: value })),
    setAddQualityTags: (value: boolean) => config.updateDraft((current) => ({ ...current, add_quality_tags: value })),
    setUndesiredContentPreset: (value: number) => config.updateDraft((current) => ({ ...current, undesired_content_preset: value })),
  };
}

/** The prompt settings a panel renders and edits. */
export type NovelAiPromptSettings = ReturnType<typeof useNovelAiPromptSettings>;
