import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { toFileUrl } from "../shared/format";
import { DeleteIcon, PromptLibraryIcon, ResetIcon, UploadIcon } from "../shared/icons";
import { cx, focusResetClass, inputClass } from "../shared/styles";
import type { ImageSizePreset, ImageStudioFormState } from "./types";

type RolePickerItem = {
  id: string;
  label: string;
  avatarAbs: string | null;
};

type ImageFormPanelProps = {
  bridgeReady: boolean;
  form: ImageStudioFormState;
  nsfwEnabled: boolean;
  addQualityTags: boolean;
  undesiredContentPreset: number;
  roleItems: RolePickerItem[];
  validationError: string;
  submitting: boolean;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onOpenPromptTagLibrary: () => void;
  onSubmit: () => void;
  onToggleNsfwEnabled: () => void;
  onToggleAddQualityTags: () => void;
  onChangeUndesiredContentPreset: (value: number) => void;
};

type ImageSelectOption<T extends string> = {
  id: T;
  label: string;
};

const sizeOptions: Array<ImageSelectOption<ImageSizePreset>> = [
  { id: "square", label: "1024 × 1024" },
  { id: "landscape", label: "1216 × 832" },
  { id: "portrait", label: "832 × 1216" },
  { id: "custom", label: "自定义" },
];

function clampCustomDimensionInput(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const digitsOnly = trimmed.replace(/[^\d]/g, "");
  if (!digitsOnly) return "";
  const parsed = Number(digitsOnly);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  return String(Math.min(1024, Math.trunc(parsed)));
}

function hasPositiveIntegerText(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  return /^\d+$/.test(trimmed) && Number(trimmed) > 0;
}

export function ImageFormPanel({
  bridgeReady,
  form,
  nsfwEnabled,
  addQualityTags,
  undesiredContentPreset,
  roleItems,
  validationError,
  submitting,
  onChange,
  onPickBaseImage,
  onOpenPromptTagLibrary,
  onSubmit,
  onToggleNsfwEnabled,
  onToggleAddQualityTags,
  onChangeUndesiredContentPreset,
}: ImageFormPanelProps) {
  const [promptTab, setPromptTab] = useState<"prompt" | "negative">("prompt");
  const [rolePanelOpen, setRolePanelOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const rolePanelRef = useRef<HTMLDivElement | null>(null);
  const settingsPanelRef = useRef<HTMLDivElement | null>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const selectClass = cx(
    inputClass,
    "h-11 appearance-none py-0 pr-10 text-sm leading-5 focus:border-[#D8DCE2] focus-visible:border-[#D8DCE2]",
  );
  const promptTextareaClass = cx(
    inputClass,
    "min-h-[96px] resize-none overflow-hidden rounded-md border-[#D6DCE3] px-3 py-2 leading-7 shadow-none hover:border-[#D6DCE3] focus:border-[#D6DCE3] focus-visible:border-[#D6DCE3]",
  );
  const segmentedControlClassName = "grid min-w-0 flex-1 grid-cols-2 rounded-md bg-[#F3F5F7] p-1";
  const segmentedButtonBaseClassName = "min-w-0 rounded-md px-3 py-1.5 text-[13px] font-semibold transition";
  const customSizeReady = form.sizePreset !== "custom"
    || (hasPositiveIntegerText(form.customWidth) && hasPositiveIntegerText(form.customHeight));
  const generateDisabled =
    !bridgeReady
    || submitting
    || Boolean(validationError)
    || !customSizeReady
    || !form.prompt.trim();

  const activeRole = useMemo(
    () => roleItems.find((item) => item.id === form.roleId) ?? null,
    [form.roleId, roleItems],
  );
  const currentAvatarLabel = activeRole?.label.slice(0, 1).toUpperCase() || "?";

  useEffect(() => {
    function handlePointerDown(event: PointerEvent): void {
      const target = event.target as Node | null;
      if (rolePanelRef.current && !rolePanelRef.current.contains(target)) {
        setRolePanelOpen(false);
      }
      if (settingsPanelRef.current && !settingsPanelRef.current.contains(target)) {
        setSettingsOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  useLayoutEffect(() => {
    const textarea = promptTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [promptTab, form.prompt, form.negativePrompt]);

  function formatSliderValue(value: number): string {
    return value.toFixed(2).replace(/\.?0+$/, "");
  }

  return (
    <section className="grid min-h-0 min-w-0 content-start gap-4 rounded-[24px] border border-[#E4EAF0] bg-white p-5">
      <div className="flex items-center gap-2">
      <div className="relative min-w-0 flex-1" ref={rolePanelRef}>
        <button
          type="button"
          className="flex h-11 w-full min-w-0 items-center gap-3 rounded-md border border-[#D8DCE2] bg-[#F3F5F7] px-3 pr-4 text-left transition hover:border-[#D8DCE2] focus:outline-none focus:ring-0 focus-visible:border-[#D8DCE2]"
          aria-expanded={rolePanelOpen}
          onClick={() => setRolePanelOpen((current) => !current)}
        >
          {activeRole?.avatarAbs ? (
            <img
              className="h-7 w-7 rounded-full object-cover"
              src={toFileUrl(activeRole.avatarAbs)}
              alt={activeRole.label}
            />
          ) : (
            <span className="grid h-7 w-7 place-items-center rounded-full bg-[#F3F5F7] text-[12px] font-semibold text-[#20242A]">
              {currentAvatarLabel}
            </span>
          )}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-[#20242A]">{activeRole?.label || "选择角色"}</span>
          <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 flex-none fill-current text-[#737781]" aria-hidden="true">
            <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
          </svg>
        </button>
        {rolePanelOpen ? (
          <div className="absolute inset-x-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-md border border-[#D8DCE2] bg-white p-2">
            <div className="grid gap-1">
              {roleItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={cx(
                    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition hover:bg-[#F5F6F8] focus:outline-none focus:ring-0",
                    form.roleId === item.id && "bg-[#F5F6F8]",
                  )}
                  onClick={() => {
                    onChange({ roleId: item.id });
                    setRolePanelOpen(false);
                  }}
                >
                  {item.avatarAbs ? (
                    <img className="h-9 w-9 rounded-full object-cover" src={toFileUrl(item.avatarAbs)} alt={item.label} />
                  ) : (
                    <span className="grid h-9 w-9 place-items-center rounded-full bg-[#F3F5F7] text-[12px] font-semibold text-[#20242A]">
                      {item.label.slice(0, 1).toUpperCase()}
                    </span>
                  )}
                  <span className="truncate text-sm text-[#20242A]">{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <button type="button" className="inline-flex h-11 w-11 flex-none items-center justify-center rounded-md border border-[#D6DCE3] bg-[#F3F5F7] text-[#666F7A] transition hover:border-[#D6DCE3] hover:text-[#20242A] focus:outline-none focus:ring-0 focus-visible:border-[#D6DCE3]" aria-label="打开提示词库" title="打开提示词库" onClick={onOpenPromptTagLibrary}>
        <PromptLibraryIcon className="h-5 w-5 fill-current" />
      </button>
      </div>

      <div className="grid gap-2">
        <div className="rounded-[18px] border border-[#E4EAF0] bg-white p-3">
          <div className="mb-3 flex items-start gap-2">
            <div className={cx(segmentedControlClassName, "max-w-[calc(100%-2.75rem)]")}>
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
                <span className="block truncate">Base Prompt</span>
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
                <span className="block truncate">Undesired Content</span>
              </button>
            </div>
            <div className="relative ml-auto flex-none" ref={settingsPanelRef}>
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#D6DCE3] bg-[#F3F5F7] text-[#666F7A] transition hover:border-[#D6DCE3] hover:text-[#20242A] focus:outline-none focus:ring-0 focus-visible:border-[#D6DCE3]"
                aria-label="Prompt 设置"
                aria-expanded={settingsOpen}
                onClick={() => setSettingsOpen((current) => !current)}
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4 fill-current" aria-hidden="true">
                  <path d="M19.14 12.94a7.43 7.43 0 0 0 .05-.94 7.43 7.43 0 0 0-.05-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.08 7.08 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54a7.08 7.08 0 0 0-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.71 8.84a.5.5 0 0 0 .12.64l2.03 1.58a7.43 7.43 0 0 0-.05.94 7.43 7.43 0 0 0 .05.94l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.39 1.04.71 1.63.94l.36 2.54a.5.5 0 0 0 .5.42h3.84a.5.5 0 0 0 .5-.42l.36-2.54c.59-.23 1.13-.55 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64ZM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7Z" />
                </svg>
              </button>
              {settingsOpen ? (
                <div className="absolute right-0 top-[calc(100%+0.5rem)] z-20 w-[320px] max-w-[calc(100vw-2rem)] rounded-md border border-[#D6DCE3] bg-[#F3F5F7] p-4">
                  <div className="mb-4 flex items-center gap-2 border-b border-[#D6DCE3] pb-3">
                    <div className="rounded-md bg-white px-2 py-1 text-xs font-medium text-[#20242A]">Settings</div>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-[#20242A]">NSFW</div>
                    <button
                      type="button"
                      className={cx(
                        "relative inline-flex h-7 w-12 rounded-full transition",
                        focusResetClass,
                        nsfwEnabled ? "bg-[#20242A]" : "bg-[#BFC6D0]",
                      )}
                      aria-pressed={nsfwEnabled}
                      onClick={onToggleNsfwEnabled}
                    >
                      <span
                        className={cx(
                          "absolute top-1 h-5 w-5 rounded-full bg-white transition",
                          nsfwEnabled ? "left-6" : "left-1",
                        )}
                      />
                    </button>
                  </div>
                  <div className="mt-4 flex items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-[#20242A]">Add Quality Tags</div>
                    <button
                      type="button"
                      className={cx(
                        "relative inline-flex h-7 w-12 rounded-full transition",
                        focusResetClass,
                        addQualityTags ? "bg-[#20242A]" : "bg-[#BFC6D0]",
                      )}
                      aria-pressed={addQualityTags}
                      onClick={onToggleAddQualityTags}
                    >
                      <span
                        className={cx(
                          "absolute top-1 h-5 w-5 rounded-full bg-white transition",
                          addQualityTags ? "left-6" : "left-1",
                        )}
                      />
                    </button>
                  </div>
                  <div className="mt-4 grid gap-2">
                    <div className="text-sm font-semibold text-[#20242A]">Undesired Content Preset</div>
                    <div className="relative">
                      <select
                        className={selectClass}
                        value={String(undesiredContentPreset)}
                        onChange={(event) => onChangeUndesiredContentPreset(Number(event.target.value) || 0)}
                      >
                        <option value="0">None</option>
                        <option value="1">Light</option>
                        <option value="2">Heavy</option>
                      </select>
                      <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
                        <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
                          <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
                        </svg>
                      </span>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          <textarea
            ref={promptTextareaRef}
            className={promptTextareaClass}
            rows={4}
            value={promptTab === "prompt" ? form.prompt : form.negativePrompt}
            onChange={(event) => (
              promptTab === "prompt"
                ? onChange({ prompt: event.target.value })
                : onChange({ negativePrompt: event.target.value })
            )}
          />
          <div className="mt-3 border-t border-[#E7EAF0] pt-3">
            {form.baseImagePath ? (
              <div className="relative overflow-hidden rounded-[18px] border border-[#D6DCE3] bg-transparent">
                <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(13,18,28,0.08)_0%,rgba(13,18,28,0.16)_56%,rgba(13,18,28,0.22)_100%)]" />
                <img
                  className="block h-[220px] w-full object-cover"
                  src={toFileUrl(form.baseImagePath)}
                  alt="Base image preview"
                />
                <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <div className="text-[18px] font-semibold leading-none tracking-[-0.02em] text-white">Image2Image</div>
                    <div className="mt-1 text-[11px] text-white/72">Transform your image.</div>
                  </div>
                  <div className="flex flex-none items-center gap-2">
                      <button
                        type="button"
                        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/12 bg-[rgba(21,25,34,0.32)] text-white/85 transition hover:border-white/24 hover:bg-[rgba(21,25,34,0.42)] hover:text-white focus:outline-none"
                        aria-label="重新选择 Base Img"
                        onClick={onPickBaseImage}
                      >
                      <ResetIcon className="h-4 w-4 fill-current" />
                    </button>
                      <button
                        type="button"
                        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-white/12 bg-[rgba(21,25,34,0.32)] text-white/85 transition hover:border-white/24 hover:bg-[rgba(21,25,34,0.42)] hover:text-white focus:outline-none"
                        aria-label="移除 Base Img"
                        onClick={() => onChange({ baseImagePath: "" })}
                      >
                      <DeleteIcon className="h-4 w-4 fill-current" />
                    </button>
                  </div>
                </div>
                <div className="absolute inset-x-0 bottom-0 p-4">
                  <div className="grid gap-3 rounded-[18px] bg-transparent px-1 py-1">
                    <label className="grid gap-2">
                      <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-white">
                        <span>Strength</span>
                        <span className="text-white/80">{formatSliderValue(form.strength)}</span>
                      </div>
                      <input
                        className="accent-white"
                        type="range"
                        min="0.01"
                        max="1"
                        step="0.01"
                        value={form.strength}
                        onChange={(event) => onChange({ strength: Number(event.target.value) })}
                      />
                    </label>
                    <label className="grid gap-2">
                      <div className="flex items-center justify-between gap-3 text-[13px] font-semibold text-white">
                        <span>Noise</span>
                        <span className="text-white/80">{formatSliderValue(form.noise)}</span>
                      </div>
                      <input
                        className="accent-white"
                        type="range"
                        min="0"
                        max="0.99"
                        step="0.01"
                        value={form.noise}
                        onChange={(event) => onChange({ noise: Number(event.target.value) })}
                      />
                    </label>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex min-w-0 items-center justify-between gap-3 border-t border-[#E7EAF0] pt-3">
                <div className="min-w-0 flex-1 text-[15px] text-[#5B616A]">Add a Base Img (Optional)</div>
                <div className="flex flex-none items-center gap-2">
                    <button
                      type="button"
                      className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-[#D6DCE3] bg-[#F3F5F7] text-[#666F7A] transition hover:border-[#D6DCE3] hover:text-[#20242A] focus:outline-none focus:ring-0 focus-visible:border-[#D6DCE3]"
                      aria-label="上传 Base Img"
                      onClick={onPickBaseImage}
                    >
                    <UploadIcon className="h-4.5 w-4.5 fill-current" />
                  </button>
                </div>
              </div>
            )}
          </div>
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
              onChange={(event) => onChange({ customWidth: clampCustomDimensionInput(event.target.value) })}
              placeholder="宽度"
            />
            <input
              className={cx(inputClass, "bg-white")}
              value={form.customHeight}
              onChange={(event) => onChange({ customHeight: clampCustomDimensionInput(event.target.value) })}
              placeholder="高度"
            />
          </div>
        ) : null}
      </div>

      {validationError ? (
        <div className="rounded-md border border-[rgba(176,58,58,0.18)] bg-[#FFF1F1] px-3 py-2 text-[12px] leading-5 text-[#9A2F2F]">
          {validationError}
        </div>
      ) : null}

      <button
        className={cx(
          "rounded-md bg-[#1F1F1F] px-4 py-3 text-sm text-white transition hover:bg-[#2A2A2A] disabled:cursor-default disabled:opacity-40",
          focusResetClass,
        )}
        type="button"
        disabled={generateDisabled}
        onClick={onSubmit}
      >
        {submitting ? "生成中..." : "生成"}
      </button>
    </section>
  );
}
