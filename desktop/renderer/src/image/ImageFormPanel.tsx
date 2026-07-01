import { useMemo, useState } from "react";
import { cx, inputClass, textareaClass } from "../shared/styles";
import type { ImageMode, ImageSizePreset, ImageStudioFormState } from "./types";

type ImageSelectOption<T extends string> = {
  id: T;
  label: string;
};

type ImageFormPanelProps = {
  bridgeReady: boolean;
  form: ImageStudioFormState;
  modelOptions: ReadonlyArray<ImageSelectOption<string>>;
  roleOptions: ReadonlyArray<ImageSelectOption<string>>;
  samplerOptions: ReadonlyArray<ImageSelectOption<string>>;
  validationError: string;
  submitting: boolean;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
};

const sizeOptions: Array<ImageSelectOption<ImageSizePreset>> = [
  { id: "landscape", label: "宽屏" },
  { id: "square", label: "正方形" },
  { id: "portrait", label: "竖屏" },
  { id: "custom", label: "自定义" },
];

const modeOptions: Array<ImageSelectOption<ImageMode>> = [
  { id: "txt2img", label: "文生图" },
  { id: "img2img", label: "图生图" },
];

function formatDisplayModel(label: string) {
  return label === "普通模型" ? "NAI Diffusion V4.5 Curated" : "NAI Diffusion V4.5 Full";
}

export function ImageFormPanel({
  bridgeReady,
  form,
  modelOptions,
  roleOptions,
  samplerOptions,
  validationError,
  submitting,
  onChange,
  onPickBaseImage,
  onSubmit,
}: ImageFormPanelProps) {
  const [promptTab, setPromptTab] = useState<"prompt" | "negative">("prompt");
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [isBaseImageToolsOpen, setIsBaseImageToolsOpen] = useState(form.mode === "img2img");
  const selectClass = cx(
    inputClass,
    "h-11 rounded-none border-[#D6DCE3] bg-[#F3F5F7] py-0 pr-10 text-sm leading-5 shadow-none hover:border-primary/40 focus:border-primary focus:bg-primary/[0.03]",
  );
  const promptTextareaClass = cx(
    textareaClass,
    "min-h-[176px] resize-none rounded-none border-[#D6DCE3] bg-[#F3F5F7] px-3 py-2 leading-7 shadow-none hover:border-primary focus:border-primary focus:bg-primary/[0.03]",
  );
  const segmentedControlClassName = "inline-flex rounded-xl bg-[#F5F6F8] p-1";
  const segmentedButtonBaseClassName = "rounded-lg px-3 py-1.5 text-[13px] font-semibold transition";
  const baseImageRangeClassName =
    "mt-2 w-full cursor-pointer appearance-none bg-transparent focus:outline-none [&::-webkit-slider-runnable-track]:h-2 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-[#D6DCE3] [&::-webkit-slider-thumb]:mt-[-4px] [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-0 [&::-webkit-slider-thumb]:bg-[#1F2937] [&::-moz-range-track]:h-2 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-[#D6DCE3] [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-[#1F2937]";

  const summarySampler = useMemo(() => {
    const matched = samplerOptions.find((option) => option.id === form.sampler);
    return matched?.label || form.sampler;
  }, [form.sampler, samplerOptions]);

  return (
    <section className="grid min-h-0 content-start gap-3">
      <div className="rounded-[18px] border border-[#E4EAF0] bg-white p-3 shadow-none">
        <div className="relative">
          <select
            className={selectClass}
            value={form.model}
            onChange={(event) => onChange({ model: event.target.value })}
          >
            {modelOptions.map((option) => (
              <option key={option.id} value={option.id}>{`${option.label} · ${formatDisplayModel(option.label)}`}</option>
            ))}
          </select>
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
            <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
              <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
            </svg>
          </span>
        </div>
      </div>

      <div className="rounded-[18px] border border-[#E4EAF0] bg-white p-3 shadow-none">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className={segmentedControlClassName}>
            <button
              type="button"
              className={cx(
                segmentedButtonBaseClassName,
                promptTab === "prompt"
                  ? "bg-white text-[#20242A] shadow-sm"
                  : "bg-transparent text-[#5B616A] hover:bg-white hover:text-[#20242A]",
              )}
              onClick={() => setPromptTab("prompt")}
            >
              Base Prompt
            </button>
            <button
              type="button"
              className={cx(
                segmentedButtonBaseClassName,
                promptTab === "negative"
                  ? "bg-white text-[#20242A] shadow-sm"
                  : "bg-transparent text-[#5B616A] hover:bg-white hover:text-[#20242A]",
              )}
              onClick={() => setPromptTab("negative")}
            >
              Undesired Content
            </button>
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#D6DCE3] bg-[#F3F5F7] text-[#666F7A] transition hover:border-primary/40 hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
            aria-label="Prompt 设置"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
              <path d="M19.14 12.94a7.43 7.43 0 0 0 .05-.94 7.43 7.43 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.08 7.08 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54a7.08 7.08 0 0 0-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.71 8.84a.5.5 0 0 0 .12.64l2.03 1.58a7.43 7.43 0 0 0-.05.94 7.43 7.43 0 0 0 .05.94l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.39 1.04.71 1.63.94l.36 2.54a.5.5 0 0 0 .5.42h3.84a.5.5 0 0 0 .5-.42l.36-2.54c.59-.23 1.13-.55 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64ZM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7Z" />
            </svg>
          </button>
        </div>
        <textarea
          className={promptTextareaClass}
          value={promptTab === "prompt" ? form.prompt : form.negativePrompt}
          onChange={(event) => (
            promptTab === "prompt"
              ? onChange({ prompt: event.target.value })
              : onChange({ negativePrompt: event.target.value })
          )}
        />
        <div className="mt-3 border-t border-[#E7EAF0] pt-3">
          {!form.baseImagePath ? (
            <div className="flex items-center justify-between gap-3">
              <div className="text-[15px] text-[#5B616A]">Add a Base Img (Optional)</div>
              <button
                type="button"
                className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-[#D6DCE3] bg-[#F3F5F7] text-[#666F7A] transition hover:border-primary/40 hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
                aria-label="上传 Base Img"
                onClick={onPickBaseImage}
              >
                <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true">
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7v2H5v14h14V12h2v7a2 2 0 0 1-2 2Z" />
                  <path d="M17 3h-2v4h-4v2h4v4h2V9h4V7h-4V3Z" />
                </svg>
              </button>
            </div>
          ) : (
            <div className="relative overflow-hidden rounded-md border border-[#E4EAF0] bg-white">
              <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(59,130,246,0.08),rgba(255,255,255,0.85))]" />
              <div className="relative p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[15px] font-semibold leading-6 text-[#20242A]">Image2Image</div>
                    <div className="mt-1 text-[13px] leading-5 text-[#5B616A]">Transform your image.</div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div className="flex overflow-hidden rounded-md border border-[#D6DCE3] bg-white/90">
                      <button
                        type="button"
                        className="inline-flex h-11 w-11 items-center justify-center text-[#666F7A] transition hover:bg-[#F3F5F7] hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
                        aria-label="更换 Base Img"
                        onClick={onPickBaseImage}
                      >
                        <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true">
                          <path d="M12 6V3L8 7l4 4V8c2.76 0 5 2.24 5 5a5 5 0 0 1-8.66 3.54l-1.42 1.42A7 7 0 0 0 19 13c0-3.87-3.13-7-7-7Z" />
                          <path d="M6 13a5 5 0 0 1 8.66-3.54l1.42-1.42A7 7 0 0 0 5 13a7 7 0 0 0 7 7v3l4-4-4-4v3c-2.76 0-5-2.24-5-5Z" />
                        </svg>
                      </button>
                      <span className="h-11 w-px bg-[#D6DCE3]" aria-hidden="true" />
                      <button
                        type="button"
                        className="inline-flex h-11 w-11 items-center justify-center text-[#666F7A] transition hover:bg-[#F3F5F7] hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
                        aria-label="移除 Base Img"
                        onClick={() => onChange({ baseImagePath: "", mode: "txt2img" })}
                      >
                        <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true">
                          <path d="M7 21a2 2 0 0 1-2-2V7h14v12a2 2 0 0 1-2 2H7Zm3-10v7h2v-7h-2Zm4 0v7h2v-7h-2ZM7 4h3.5l1-1h1l1 1H17v2H7V4Z" />
                        </svg>
                      </button>
                    </div>
                    <button
                      type="button"
                      className="inline-flex h-11 w-11 items-center justify-center text-[#666F7A] transition hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
                      aria-label={isBaseImageToolsOpen ? "收起 Base Img 工具" : "展开 Base Img 工具"}
                      onClick={() => setIsBaseImageToolsOpen((current) => !current)}
                    >
                      <svg viewBox="0 0 24 24" className={cx("h-5 w-5 fill-current transition-transform", isBaseImageToolsOpen && "rotate-180")} aria-hidden="true">
                        <path d="M7 10l5 5 5-5z" />
                      </svg>
                    </button>
                  </div>
                </div>
                {isBaseImageToolsOpen ? (
                  <div className="mt-4 space-y-4">
                    <label className="block">
                      <div className="flex items-center justify-between text-[13px] font-semibold leading-5 text-[#20242A]">
                        <span>Strength</span>
                        <span>{form.strength}</span>
                      </div>
                      <input
                        type="range"
                        min="0.01"
                        max="1"
                        step="0.01"
                        value={form.strength}
                        className={baseImageRangeClassName}
                        onChange={(event) => onChange({ strength: event.target.value })}
                      />
                    </label>
                    <label className="block">
                      <div className="flex items-center justify-between text-[13px] font-semibold leading-5 text-[#20242A]">
                        <span>Noise</span>
                        <span>{form.noise}</span>
                      </div>
                      <input
                        type="range"
                        min="0"
                        max="0.99"
                        step="0.01"
                        value={form.noise}
                        className={baseImageRangeClassName}
                        onChange={(event) => onChange({ noise: event.target.value })}
                      />
                    </label>
                    <button
                      type="button"
                      className="inline-flex h-11 items-center gap-2 rounded-md border border-[#D6DCE3] bg-white px-4 text-[14px] font-semibold text-[#20242A] transition hover:border-primary/40 hover:text-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                      disabled
                    >
                      <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current" aria-hidden="true">
                        <path d="M19 11h-6V5h-2v6H5v2h6v6h2v-6h6z" />
                      </svg>
                      <span>Inpaint Image</span>
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>

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

      <div className="rounded-t-[20px] border border-[#D6DCE3] bg-[#F3F5F7] px-3 py-3 shadow-[0_-16px_36px_rgba(15,23,42,0.12)]">
        {!isAdvancedOpen ? (
          <button
            type="button"
            className="grid h-14 w-full grid-cols-[max-content_max-content_max-content_minmax(0,1fr)_auto] items-center gap-[10px] rounded-t-2xl border border-[#D6DCE3] bg-white px-3 text-left text-[#20242A] transition hover:bg-[#F7F8FB] focus:outline-none focus:ring-2 focus:ring-primary/20"
            aria-expanded={isAdvancedOpen}
            onClick={() => setIsAdvancedOpen(true)}
          >
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="text-xs font-medium leading-none text-[#6B7280]">Steps</div>
              <div className="text-sm font-semibold leading-none">{form.steps}</div>
            </div>
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="text-xs font-medium leading-none text-[#6B7280]">Guidance</div>
              <div className="text-sm font-semibold leading-none">{form.strength}</div>
            </div>
            <div className="flex min-w-0 flex-col gap-0.5">
              <div className="text-xs font-medium leading-none text-[#6B7280]">Seed</div>
              <div className="text-sm font-semibold leading-none">{form.seed.trim() ? form.seed : "N/A"}</div>
            </div>
            <div className="flex min-w-0 flex-col gap-0.5 overflow-hidden">
              <div className="truncate text-xs font-medium leading-none text-[#6B7280]">Sampler</div>
              <div className="truncate text-sm font-semibold leading-none">{summarySampler}</div>
            </div>
            <div className="flex items-center justify-end">
              <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                <path d="M7 14l5-5 5 5z" />
              </svg>
            </div>
          </button>
        ) : (
          <div className="rounded-t-2xl border border-[#D6DCE3] bg-[#F3F5F7] px-4 pb-4 pt-4">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-[#20242A]">AI Settings</div>
              <button
                type="button"
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-[#666F7A] transition hover:bg-black/5 hover:text-[#20242A] focus:outline-none focus:ring-2 focus:ring-primary/20"
                aria-label="收起 AI 设置"
                onClick={() => setIsAdvancedOpen(false)}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                  <path d="M7 10l5 5 5-5z" />
                </svg>
              </button>
            </div>
            <div className="space-y-4">
              <label className="block">
                <div className="mb-2 flex items-center justify-between pr-1">
                  <span className="text-sm font-semibold text-[#20242A]">{`Steps: ${form.steps}`}</span>
                </div>
                <input
                  className="range range-xs w-full"
                  type="range"
                  min="1"
                  max="28"
                  step="1"
                  value={form.steps}
                  onChange={(event) => onChange({ steps: event.target.value })}
                />
              </label>

              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-2">
                  <div className="text-sm font-semibold text-[#20242A]">Seed</div>
                  <input
                    className={cx(selectClass, "pr-3")}
                    type="number"
                    min="0"
                    value={form.seed}
                    placeholder="Enter a seed"
                    onChange={(event) => onChange({ seed: event.target.value })}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <div className="text-sm font-semibold text-[#20242A]">Sampler</div>
                  <div className="relative">
                    <select
                      className={selectClass}
                      value={form.sampler}
                      onChange={(event) => onChange({ sampler: event.target.value })}
                    >
                      {samplerOptions.map((option) => (
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
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between pr-1">
                  <span className="text-sm font-semibold text-[#20242A]">{`Strength: ${form.strength}`}</span>
                </div>
                <input
                  className="range range-xs w-full"
                  type="range"
                  min="0.01"
                  max="1"
                  step="0.01"
                  value={form.strength}
                  onChange={(event) => onChange({ strength: event.target.value })}
                />
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between pr-1">
                  <span className="text-sm font-semibold text-[#20242A]">{`Noise: ${form.noise}`}</span>
                </div>
                <input
                  className="range range-xs w-full"
                  type="range"
                  min="0"
                  max="0.99"
                  step="0.01"
                  value={form.noise}
                  onChange={(event) => onChange({ noise: event.target.value })}
                />
              </div>

              <div>
                <div className="mb-2 text-sm font-semibold text-[#20242A]">Resolution</div>
                <div className="grid gap-2">
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
                  <div className="grid h-11 grid-cols-[minmax(0,1fr)_10px_minmax(0,1fr)] items-center gap-1 rounded-none border border-[#D6DCE3] bg-[#F3F5F7] px-3 py-2 shadow-sm">
                    <input
                      className="min-w-0 appearance-none bg-transparent text-center text-xs font-semibold leading-none tabular-nums text-[#20242A] focus:outline-none [-moz-appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                      type="number"
                      min={1}
                      step={64}
                      value={form.sizePreset === "custom" ? form.customWidth : (form.sizePreset === "landscape" ? "1408" : form.sizePreset === "portrait" ? "704" : "1024")}
                      onChange={(event) => onChange({ customWidth: event.target.value, sizePreset: "custom" })}
                    />
                    <span className="text-center text-xs font-medium text-[#6B7280]">×</span>
                    <input
                      className="min-w-0 appearance-none bg-transparent text-center text-xs font-semibold leading-none tabular-nums text-[#20242A] focus:outline-none [-moz-appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                      type="number"
                      min={1}
                      step={64}
                      value={form.sizePreset === "custom" ? form.customHeight : (form.sizePreset === "landscape" ? "704" : form.sizePreset === "portrait" ? "1408" : "1024")}
                      onChange={(event) => onChange({ customHeight: event.target.value, sizePreset: "custom" })}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {validationError ? (
        <div className="rounded-md border border-[rgba(176,58,58,0.18)] bg-[#FFF1F1] px-3 py-2 text-[12px] leading-5 text-[#9A2F2F]">
          {validationError}
        </div>
      ) : null}

      <button
        className="rounded-md bg-[#38B2AC] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#2FA39D] focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-default disabled:opacity-40"
        type="button"
        disabled={!bridgeReady || submitting || Boolean(validationError)}
        onClick={onSubmit}
      >
        {submitting ? "生成中..." : "Generate 1 Image"}
      </button>
    </section>
  );
}
