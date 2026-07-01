import { cx, ghostButtonClass, inputClass, textareaClass } from "../shared/styles";
import type { ImageMode, ImageSizePreset, ImageStudioFormState } from "./types";
import { useState } from "react";

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
  const [promptTab, setPromptTab] = useState<"prompt" | "negative">("prompt");
  const selectClass = cx(
    inputClass,
    "h-11 appearance-none bg-white py-0 pr-10 text-sm leading-5",
  );
  const promptTextareaClass = cx(
    textareaClass,
    "min-h-[176px] resize-none rounded-none border-[#D6DCE3] bg-[#F3F5F7] px-3 py-2 leading-7 shadow-none hover:border-primary focus:border-primary focus:bg-primary/[0.03]",
  );
  const segmentedControlClassName = "inline-flex rounded-xl bg-[#F5F6F8] p-1";
  const segmentedButtonBaseClassName = "rounded-lg px-3 py-1.5 text-[13px] font-semibold transition";

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
        <div className="rounded-[18px] border border-[#E4EAF0] bg-white p-3">
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
        </div>
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
