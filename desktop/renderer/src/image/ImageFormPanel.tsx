import { cx, ghostButtonClass, inputClass, textareaClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import type { ImageMode, ImageSizePreset, ImageStudioFormState } from "./types";

type ImageFormPanelProps = {
  activeRole: RoleRecord | null;
  autoWritebackRoleAssets: boolean;
  bridgeReady: boolean;
  form: ImageStudioFormState;
  validationError: string;
  submitting: boolean;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
};

const sizeOptions: Array<{ id: ImageSizePreset; label: string }> = [
  { id: "square", label: "1024 × 1024" },
  { id: "landscape", label: "1216 × 832" },
  { id: "portrait", label: "832 × 1216" },
  { id: "custom", label: "自定义" },
];

const modeOptions: Array<{ id: ImageMode; label: string }> = [
  { id: "txt2img", label: "文生图" },
  { id: "img2img", label: "图生图" },
];

export function ImageFormPanel({
  activeRole,
  autoWritebackRoleAssets,
  bridgeReady,
  form,
  validationError,
  submitting,
  onChange,
  onPickBaseImage,
  onSubmit,
}: ImageFormPanelProps) {
  return (
    <section className="grid min-h-0 content-start gap-4 rounded-[24px] border border-[#E4EAF0] bg-[#FBFCFE] p-5">
      <div className="grid gap-1">
        <div className="text-sm font-semibold text-[#20242A]">生成参数</div>
        <div className="text-[12px] leading-5 text-[#7B7F87]">
          {activeRole ? activeRole.name : "未绑定角色"}
          {activeRole && autoWritebackRoleAssets ? " · 自动写回" : ""}
        </div>
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">模式</div>
        <div className="grid grid-cols-2 gap-2">
          {modeOptions.map((option) => (
            <button
              key={option.id}
              className={cx(
                "rounded-md border px-3 py-2 text-sm transition",
                form.mode === option.id
                  ? "border-[#272536] bg-[#272536] text-white"
                  : "border-[#D8DCE2] bg-white text-[#32363C] hover:border-[#9AA3B2]",
              )}
              type="button"
              onClick={() => onChange({ mode: option.id })}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">Prompt</div>
        <textarea
          className={cx(textareaClass, "min-h-[140px] bg-white")}
          value={form.prompt}
          onChange={(event) => onChange({ prompt: event.target.value })}
        />
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">Negative Prompt</div>
        <textarea
          className={cx(textareaClass, "min-h-[96px] bg-white")}
          value={form.negativePrompt}
          onChange={(event) => onChange({ negativePrompt: event.target.value })}
        />
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">尺寸</div>
        <div className="grid grid-cols-2 gap-2">
          {sizeOptions.map((option) => (
            <button
              key={option.id}
              className={cx(
                "rounded-md border px-3 py-2 text-sm transition",
                form.sizePreset === option.id
                  ? "border-[#272536] bg-[#272536] text-white"
                  : "border-[#D8DCE2] bg-white text-[#32363C] hover:border-[#9AA3B2]",
              )}
              type="button"
              onClick={() => onChange({ sizePreset: option.id })}
            >
              {option.label}
            </button>
          ))}
        </div>
        {form.sizePreset === "custom" ? (
          <div className="grid gap-2 md:grid-cols-2">
            <input
              className={cx(inputClass, "bg-white")}
              value={form.customWidth}
              onChange={(event) => onChange({ customWidth: event.target.value })}
              placeholder="宽度"
            />
            <input
              className={cx(inputClass, "bg-white")}
              value={form.customHeight}
              onChange={(event) => onChange({ customHeight: event.target.value })}
              placeholder="高度"
            />
          </div>
        ) : null}
      </div>

      {form.mode === "img2img" ? (
        <div className="grid gap-2">
          <div className="text-xs font-medium text-[#4A4F57]">输入图</div>
          <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={onPickBaseImage}>
            选择图片
          </button>
          <div className="rounded-md border border-[#E7EAF0] bg-white px-3 py-2 text-[12px] text-[#6B7280]">
            {form.baseImagePath || "未选择"}
          </div>
        </div>
      ) : null}

      <div className="grid gap-2 md:grid-cols-2">
        <input
          className={cx(inputClass, "bg-white")}
          value={form.steps}
          onChange={(event) => onChange({ steps: event.target.value })}
          placeholder="步数"
        />
        <input
          className={cx(inputClass, "bg-white")}
          value={form.seed}
          onChange={(event) => onChange({ seed: event.target.value })}
          placeholder="Seed"
        />
        <input
          className={cx(inputClass, "bg-white")}
          value={form.sampler}
          onChange={(event) => onChange({ sampler: event.target.value })}
          placeholder="Sampler"
        />
        <input
          className={cx(inputClass, "bg-white")}
          value={form.model}
          onChange={(event) => onChange({ model: event.target.value })}
          placeholder="Model"
        />
      </div>

      {validationError ? (
        <div className="rounded-md border border-[rgba(176,58,58,0.18)] bg-[#FFF1F1] px-3 py-2 text-[12px] leading-5 text-[#9A2F2F]">
          {validationError}
        </div>
      ) : null}

      <button
        className="rounded-md bg-[#1F1F1F] px-4 py-3 text-sm text-white transition hover:bg-[#2A2A2A] disabled:cursor-default disabled:opacity-40"
        type="button"
        disabled={!bridgeReady || submitting || Boolean(validationError)}
        onClick={onSubmit}
      >
        {submitting ? "生成中..." : "生成"}
      </button>
    </section>
  );
}
