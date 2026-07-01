import { startTransition, useEffect, useMemo, useState } from "react";
import type { RoleRecord } from "../shared/types";
import type {
  ImageGenerateResult,
  ImageHistoryRecord,
  ImageStudioFormState,
} from "./types";

type UseImageStudioStateArgs = {
  active: boolean;
  activeRole: RoleRecord | null;
};

const initialForm: ImageStudioFormState = {
  prompt: "",
  negativePrompt: "",
  mode: "txt2img",
  baseImagePath: "",
  sizePreset: "square",
  customWidth: "",
  customHeight: "",
  steps: "28",
  seed: "",
  sampler: "k_euler_ancestral",
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
export function useImageStudioState({ active, activeRole }: UseImageStudioStateArgs) {
  const [form, setForm] = useState<ImageStudioFormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState<ImageHistoryRecord[]>([]);
  const [selectedRecordId, setSelectedRecordId] = useState("");
  const [latestResult, setLatestResult] = useState<ImageGenerateResult | null>(null);
  const [error, setError] = useState("");
  const [autoWritebackRoleAssets, setAutoWritebackRoleAssets] = useState(false);

  async function loadHistory(): Promise<void> {
    const response = await window.miraDesktop.invoke({
      method: "novelai.history",
      payload: {
        role_id: activeRole?.id ?? "",
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
      setAutoWritebackRoleAssets(settingsResult.formData.integrations.novelaiAutoWritebackRoleAssets);
    })();

    return () => {
      cancelled = true;
    };
  }, [active, activeRole?.id]);

  const validationError = useMemo(() => {
    if (!form.prompt.trim()) return "prompt 不能为空";
    const steps = parsePositiveInteger(form.steps);
    if (steps == null) return "steps 必须是正整数";
    if (steps > 28) return "当前仅允许 steps 不超过 28";
    if (form.mode === "img2img" && !form.baseImagePath.trim()) {
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
      mode: form.mode,
      width: form.sizePreset === "custom" ? (form.customWidth || "-") : presetSize.width,
      height: form.sizePreset === "custom" ? (form.customHeight || "-") : presetSize.height,
      steps: form.steps || "-",
      model: form.model || "-",
      seed: form.seed || "-",
    };
  }, [form]);

  async function handlePickBaseImage(): Promise<void> {
    const files = await window.miraDesktop.pickImages({ multiple: false });
    if (!files[0]) return;
    setForm((current) => ({ ...current, baseImagePath: files[0] }));
  }

  async function handleSubmit(): Promise<void> {
    if (validationError) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await window.miraDesktop.invoke({
        method: "novelai.generate",
        payload: {
          role_id: activeRole?.id ?? "",
          session_key: activeRole ? `role:${activeRole.id}` : "desktop:image-studio",
          prompt: form.prompt,
          mode: form.mode,
          base_image_path: form.baseImagePath,
          negative_prompt: form.negativePrompt,
          size_preset: form.sizePreset,
          custom_width: form.sizePreset === "custom" ? parsePositiveInteger(form.customWidth) : undefined,
          custom_height: form.sizePreset === "custom" ? parsePositiveInteger(form.customHeight) : undefined,
          steps: parsePositiveInteger(form.steps),
          seed: parsePositiveInteger(form.seed),
          sampler: form.sampler,
          model: form.model,
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

  return {
    activeRecord,
    autoWritebackRoleAssets,
    error,
    form,
    history,
    latestResult,
    requestSummary,
    selectedRecordId,
    submitting,
    validationError,
    onChange: (next: Partial<ImageStudioFormState>) => {
      setForm((current) => ({ ...current, ...next }));
    },
    onPickBaseImage: () => void handlePickBaseImage(),
    onSelectRecord: (record: ImageHistoryRecord) => setSelectedRecordId(record.id),
    onSubmit: () => void handleSubmit(),
  };
}
