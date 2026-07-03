import { startTransition, useEffect, useMemo, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type { SettingsFormData } from "../shared/types";
import type {
  ImageGenerateResult,
  ImageHistoryRecord,
  ImageStudioFormState,
} from "./types";

type UseImageStudioStateArgs = {
  active: boolean;
  activeRole: RoleRecord | null;
  roles: RoleRecord[];
};

const initialForm: ImageStudioFormState = {
  roleId: "",
  prompt: "",
  negativePrompt: "",
  mode: "txt2img",
  baseImagePath: "",
  strength: 0.7,
  noise: 0.2,
  sizePreset: "square",
  customWidth: "",
  customHeight: "",
  model: "nai-diffusion-4-5-curated",
};

function parsePositiveInteger(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) return null;
  return parsed;
}

function resolvePresetSize(sizePreset: ImageStudioFormState["sizePreset"]): {
  width: string;
  height: string;
} {
  switch (sizePreset) {
    case "landscape":
      return { width: "1216", height: "832" };
    case "portrait":
      return { width: "832", height: "1216" };
    case "custom":
      return { width: "-", height: "-" };
    case "square":
    default:
      return { width: "1024", height: "1024" };
  }
}

/** Manages image studio state so the shell sidebar and preview area stay in sync. */
export function useImageStudioState({ active, activeRole, roles }: UseImageStudioStateArgs) {
  const [form, setForm] = useState<ImageStudioFormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState<ImageHistoryRecord[]>([]);
  const [selectedRecordId, setSelectedRecordId] = useState("");
  const [latestResult, setLatestResult] = useState<ImageGenerateResult | null>(null);
  const [error, setError] = useState("");
  const [settingsFormData, setSettingsFormData] = useState<SettingsFormData | null>(null);

  const roleItems = useMemo(() => (
    roles.map((role) => ({
      id: role.id,
      label: role.name,
      avatarAbs: role.avatar_abs,
    }))
  ), [roles]);

  const nsfwEnabled = Boolean(settingsFormData?.integrations.novelaiNsfwEnabled);

  async function loadHistory(): Promise<void> {
    const response = await window.miraDesktop.invoke({
      method: "novelai.history",
      payload: {
        role_id: form.roleId,
        limit: 24,
      },
    });
    if (response.error) {
      setError(response.error.message);
      return;
    }
    const records = Array.isArray(response.payload.records)
      ? response.payload.records as ImageHistoryRecord[]
      : [];
    setHistory(records);
    setSelectedRecordId((current) => (
      records.some((record) => record.id === current)
        ? current
        : (records[0]?.id ?? "")
    ));
  }

  useEffect(() => {
    if (!active) return undefined;

    let cancelled = false;
    setLatestResult(null);
    setError("");

    void (async () => {
      const [settingsResult] = await Promise.all([
        window.miraDesktop.readSettings(),
        loadHistory(),
      ]);
      if (cancelled) return;
      setSettingsFormData(settingsResult.formData);
      setForm((current) => ({
        ...current,
        roleId: current.roleId || activeRole?.id || "",
      }));
    })();

    return () => {
      cancelled = true;
    };
  }, [active, activeRole?.id, form.roleId]);

  useEffect(() => {
    setForm((current) => {
      const roleId = current.roleId && roles.some((role) => role.id === current.roleId)
        ? current.roleId
        : (activeRole?.id ?? roles[0]?.id ?? "");
      return current.roleId === roleId ? current : { ...current, roleId };
    });
  }, [activeRole?.id, roles]);

  const resolvedMode = form.baseImagePath.trim() ? "img2img" : "txt2img";
  const resolvedModel = useMemo(() => (
    nsfwEnabled
      ? (settingsFormData?.integrations.novelaiNsfwModel?.trim() || "nai-diffusion-4-5-full")
      : (settingsFormData?.integrations.novelaiDefaultModel?.trim() || "nai-diffusion-4-5-curated")
  ), [nsfwEnabled, settingsFormData]);
  const addQualityTags = Boolean(settingsFormData?.integrations.novelaiAddQualityTags);
  const undesiredContentPreset = Number(settingsFormData?.integrations.novelaiUndesiredContentPreset ?? 0);

  const validationError = useMemo(() => {
    if (resolvedMode === "img2img" && !form.baseImagePath.trim()) {
      return "img2img 需要输入图";
    }
    if (form.sizePreset === "custom") {
      const width = parsePositiveInteger(form.customWidth);
      const height = parsePositiveInteger(form.customHeight);
      if (width == null || height == null) return "自定义尺寸必须是正整数";
      if (width > 1024 || height > 1024) return "自定义尺寸单边不能超过 1024";
      if (width * height > 1024 * 1024) return "自定义尺寸总像素不能超过 1024 × 1024";
    }
    return "";
  }, [form]);

  const activeRecord = history.find((item) => item.id === selectedRecordId) ?? history[0] ?? null;
  const requestSummary = useMemo(() => {
    const presetSize = resolvePresetSize(form.sizePreset);
    return {
      mode: resolvedMode,
      width: form.sizePreset === "custom" ? (form.customWidth || "-") : presetSize.width,
      height: form.sizePreset === "custom" ? (form.customHeight || "-") : presetSize.height,
      model: resolvedModel || "-",
    };
  }, [form, resolvedMode, resolvedModel]);

  async function handlePickBaseImage(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: false });
    if (!files[0]) return;
    setForm((current) => ({ ...current, baseImagePath: files[0] }));
  }

  async function handleSubmit(): Promise<void> {
    if (!form.prompt.trim()) {
      setError("");
      return;
    }
    if (validationError) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await window.miraDesktop.invoke({
        method: "novelai.generate",
        payload: {
          role_id: form.roleId,
          session_key: form.roleId ? `role:${form.roleId}` : "desktop:image-studio",
          prompt: form.prompt,
          mode: resolvedMode,
          base_image_path: form.baseImagePath,
          strength: resolvedMode === "img2img" ? form.strength : undefined,
          noise: resolvedMode === "img2img" ? form.noise : undefined,
          negative_prompt: form.negativePrompt,
          size_preset: form.sizePreset,
          custom_width: form.sizePreset === "custom" ? parsePositiveInteger(form.customWidth) : undefined,
          custom_height: form.sizePreset === "custom" ? parsePositiveInteger(form.customHeight) : undefined,
          model: resolvedModel,
        },
      });
      if (response.error) {
        setError(response.error.message);
        return;
      }
      const result = response.payload.result as ImageGenerateResult;
      setLatestResult(result);
      await loadHistory();
      startTransition(() => {
        setSelectedRecordId(result.record_id);
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggleNsfwEnabled(): Promise<void> {
    if (!settingsFormData) return;
    const nextFormData: SettingsFormData = {
      ...settingsFormData,
      integrations: {
        ...settingsFormData.integrations,
        novelaiNsfwEnabled: !settingsFormData.integrations.novelaiNsfwEnabled,
      },
    };
    setSettingsFormData(nextFormData);
    try {
      await window.miraDesktop.saveSettings(nextFormData);
      const refreshed = await window.miraDesktop.readSettings();
      setSettingsFormData(refreshed.formData);
    } catch (saveError) {
      setSettingsFormData(settingsFormData);
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    }
  }

  async function handleToggleAddQualityTags(): Promise<void> {
    if (!settingsFormData) return;
    const nextFormData: SettingsFormData = {
      ...settingsFormData,
      integrations: {
        ...settingsFormData.integrations,
        novelaiAddQualityTags: !settingsFormData.integrations.novelaiAddQualityTags,
      },
    };
    setSettingsFormData(nextFormData);
    try {
      await window.miraDesktop.saveSettings(nextFormData);
      const refreshed = await window.miraDesktop.readSettings();
      setSettingsFormData(refreshed.formData);
    } catch (saveError) {
      setSettingsFormData(settingsFormData);
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    }
  }

  async function handleChangeUndesiredContentPreset(value: number): Promise<void> {
    if (!settingsFormData) return;
    const nextFormData: SettingsFormData = {
      ...settingsFormData,
      integrations: {
        ...settingsFormData.integrations,
        novelaiUndesiredContentPreset: value,
      },
    };
    setSettingsFormData(nextFormData);
    try {
      await window.miraDesktop.saveSettings(nextFormData);
      const refreshed = await window.miraDesktop.readSettings();
      setSettingsFormData(refreshed.formData);
    } catch (saveError) {
      setSettingsFormData(settingsFormData);
      setError(saveError instanceof Error ? saveError.message : String(saveError));
    }
  }

  return {
    activeRecord,
    addQualityTags,
    error,
    form,
    history,
    latestResult,
    nsfwEnabled,
    undesiredContentPreset,
    requestSummary,
    roleItems,
    selectedRecordId,
    submitting,
    validationError,
    onChange: (next: Partial<ImageStudioFormState>) => {
      setForm((current) => ({ ...current, ...next }));
    },
    onPickBaseImage: () => void handlePickBaseImage(),
    onSelectRecord: (record: ImageHistoryRecord) => setSelectedRecordId(record.id),
    onSubmit: () => void handleSubmit(),
    onChangeUndesiredContentPreset: (value: number) => void handleChangeUndesiredContentPreset(value),
    onToggleAddQualityTags: () => void handleToggleAddQualityTags(),
    onToggleNsfwEnabled: () => void handleToggleNsfwEnabled(),
  };
}
