import { useEffect, useRef, useState } from "react";
import { errorMessage, usePluginHostServices, type PluginConfigValues } from "@yinfengwindy/shiori-sdk";

/**
 * Fallbacks for the two configured model ids, used only until the plugin's
 * config has loaded; the configured value always wins once it has.
 */
const defaultModelFallback = "nai-diffusion-4-5-curated";
const nsfwModelFallback = "nai-diffusion-4-5-full";

/** A field edited here whose save has not settled yet, tagged with the edit that set it. */
type PendingField = { value: unknown; edit: number };

/**
 * The plugin's config as the popover shows it: the stored values (read on
 * mount, then each stored result from `host.config.subscribe`) under this
 * component's unsettled edits. An edit shows at once and is saved as a
 * one-field patch; it stays on top until the save it started settles, so an
 * earlier save's broadcast arriving meanwhile cannot flip the control back.
 * A successful save stores the values it resolved to, so the result never
 * depends on whether the host's broadcast of it arrives first. A failed save
 * drops its edit (the stored value shows again) and raises a toast.
 */
function useNovelAiConfig() {
  const { config, feedback } = usePluginHostServices();
  const [stored, setStored] = useState<PluginConfigValues>({});
  const [pending, setPending] = useState<Record<string, PendingField>>({});
  const edits = useRef(0);
  // Whether local state may still be written: saves settle after the component may be gone.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    // Per subscription, not `mounted`: a new `config` must also silence the previous one.
    let active = true;
    // A stored result seen before the initial read resolves is newer than that read.
    let received = false;
    const unsubscribe = config.subscribe((values) => {
      received = true;
      if (active) setStored(values);
    });
    config.get().then((values) => {
      if (active && !received) setStored(values);
    }, (error: unknown) => {
      // Only an open popover needs the values; the next mount reads them again.
      if (active) feedback.error("生成设置加载失败", { detail: errorMessage(error), persona: true });
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [config, feedback]);

  const values: PluginConfigValues = { ...stored };
  for (const [field, { value }] of Object.entries(pending)) values[field] = value;

  function set(field: string, value: unknown): void {
    if (values[field] === value) return;
    const edit = ++edits.current;
    setPending((current) => ({ ...current, [field]: { value, edit } }));
    // Only the latest edit of a field clears it; an older save settling leaves the newer edit on top.
    const settle = () => {
      if (!mounted.current) return;
      setPending((current) => {
        if (current[field]?.edit !== edit) return current;
        const rest = { ...current };
        delete rest[field];
        return rest;
      });
    };
    config.save({ [field]: value }).then((saved) => {
      if (mounted.current) setStored(saved);
      settle();
    }, (error: unknown) => {
      settle();
      // Not guarded: the user's change is lost whether or not the popover is still open, so they must hear of it.
      feedback.error("生成设置保存失败", { detail: errorMessage(error), persona: true });
    });
  }

  return { values, set };
}

/**
 * The prompt-level switches that are really plugin config (NSFW, quality
 * tags, undesired-content preset), read and saved through `host.config` —
 * the same config as the plugin's settings tab, which refreshes on each
 * save — plus the model they resolve to.
 */
export function useNovelAiPromptSettings() {
  const { values, set } = useNovelAiConfig();
  const nsfwEnabled = Boolean(values.nsfw_enabled);
  const addQualityTags = Boolean(values.add_quality_tags);
  const undesiredContentPreset = Number(values.undesired_content_preset ?? 0);
  const configuredDefaultModel = typeof values.default_model === "string" ? values.default_model : "";
  const configuredNsfwModel = typeof values.nsfw_model === "string" ? values.nsfw_model : "";
  const model = nsfwEnabled
    ? (configuredNsfwModel || nsfwModelFallback)
    : (configuredDefaultModel || defaultModelFallback);

  return {
    nsfwEnabled,
    addQualityTags,
    undesiredContentPreset,
    model,
    setNsfwEnabled: (value: boolean) => set("nsfw_enabled", value),
    setAddQualityTags: (value: boolean) => set("add_quality_tags", value),
    setUndesiredContentPreset: (value: number) => set("undesired_content_preset", value),
  };
}

/** The prompt settings a panel renders and edits. */
export type NovelAiPromptSettings = ReturnType<typeof useNovelAiPromptSettings>;
