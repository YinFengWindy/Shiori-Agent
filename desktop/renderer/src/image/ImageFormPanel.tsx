import { cx, ghostButtonClass, inputClass, textareaClass } from "../shared/styles";
import type { ImageMode, ImageSizePreset, ImageStudioFormState } from "./types";

type ImageSelectOption<T extends string> = {
  id: T;
  label: string;
};

type ImageFormPanelProps = {
  bridgeReady: boolean;
  form: ImageStudioFormState;
  modelOptions: Array<ImageSelectOption<string>>;
  roleOptions: Array<ImageSelectOption<string>>;
  validationError: string;
  submitting: boolean;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
};

const sizeOptions: Array<ImageSelectOption<ImageSizePreset>> = [
  { id: "square", label: "1024 × 1024" },
  { id: "landscape", label: "1216 × 832" },
  { id: "portrait", label: "832 × 1216" },
  { id: "custom", label: "自定义" },
];

const modeOptions: Array<ImageSelectOption<ImageMode>> = [
  { id: "txt2img", label: "文生图" },
  { id: "img2img", label: "图生图" },
];

export function ImageFormPanel({
  bridgeReady,
  form,
  modelOptions,
  roleOptions,
  validationError,
  submitting,
  onChange,
  onPickBaseImage,
  onSubmit,
}: ImageFormPanelProps) {
  const selectClass = cx(
    inputClass,
    "h-11 appearance-none bg-white py-0 pr-10 text-sm leading-5",
  );

  return (
    <section className="grid min-h-0 content-start gap-4 rounded-[24px] border border-[#E4EAF0] bg-[#FBFCFE] p-5 shadow-[0_10px_28px_rgba(15,23,42,0.04)]">
      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">角色</div>
        <div className="relative">
          <select
            className={selectClass}
            value={form.roleId}
            onChange={(event) => onChange({ roleId: event.target.value })}
          >
            <option value="">不绑定角色</option>
            {roleOptions.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
            <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
              <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
            </svg>
          </span>
        </div>
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">模型</div>
        <div className="relative">
          <select
            className={selectClass}
            value={form.model}
            onChange={(event) => onChange({ model: event.target.value })}
          >
            {modelOptions.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
            <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
              <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
            </svg>
          </span>
        </div>
      </div>

      <div className="grid gap-2">
        <div className="text-xs font-medium text-[#4A4F57]">模式</div>
        <div className="relative">
          <select
            className={selectClass}
            value={form.mode}
            onChange={(event) => onChange({ mode: event.target.value as ImageMode })}
          >
            {modeOptions.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
            <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
              <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
            </svg>
          </span>
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
        <div className="relative">
          <select
            className={selectClass}
            value={form.sizePreset}
            onChange={(event) => onChange({ sizePreset: event.target.value as ImageSizePreset })}
          >
            {sizeOptions.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
            <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
              <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
            </svg>
          </span>
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

      <div className="grid gap-2">
        <input
          className={cx(inputClass, "bg-white")}
          value={form.seed}
          onChange={(event) => onChange({ seed: event.target.value })}
          placeholder="Seed"
        />
      </div>

      {validationError ? (
        <div className="rounded-md border border-[rgba(176,58,58,0.18)] bg-[#FFF1F1] px-3 py-2 text-[12px] leading-5 text-[#9A2F2F]">
          {validationError}
        </div>
      ) : null}

      <button
        className="rounded-md bg-[#1F1F1F] px-4 py-3 text-sm text-white transition hover:bg-[#2A2A2A] focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-default disabled:opacity-40"
        type="button"
        disabled={!bridgeReady || submitting || Boolean(validationError)}
        onClick={onSubmit}
      >
        {submitting ? "生成中..." : "生成"}
      </button>
    </section>
  );
}
