import { useState } from "react";
import { Sparkle } from "@phosphor-icons/react";
import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import { cx, inputClass, primaryButtonSurfaceClass } from "../../../apps/desktop/renderer/src/shared/styles";
import type { RoleRecord } from "../../../apps/desktop/renderer/src/shared/types";
import { Select, type SelectOption } from "../../../apps/desktop/renderer/src/shared/ui/Select";
import { BaseImageField } from "./BaseImageField";
import { PromptSettingsPopover } from "./PromptSettingsPopover";
import { SegmentedControl } from "./SegmentedControl";
import { SizeField, studioFieldLabelClass } from "./SizeField";
import type { ImageStudioFormState } from "./types";
import type { NovelAiPromptSettings } from "./useNovelAiPromptSettings";

type PromptPanelProps = {
  form: ImageStudioFormState;
  roles: RoleRecord[];
  settings: NovelAiPromptSettings;
  submitting: boolean;
  canSubmit: boolean;
  validationError: string;
  onChange: (next: Partial<ImageStudioFormState>) => void;
  onPickBaseImage: () => void;
  onSubmit: () => void;
};

type PromptTab = "prompt" | "negative";

/** A role's avatar at select-row size, or its initial on the accent tint. */
function RoleAvatar({ role }: { role: RoleRecord }) {
  if (role.avatar_abs) {
    return <img className="h-6 w-6 rounded-full object-cover" src={toFileUrl(role.avatar_abs)} alt="" />;
  }
  return (
    <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-softer text-caption font-semibold text-accent-text">
      {role.name.slice(0, 1).toUpperCase()}
    </span>
  );
}

/**
 * The generation form: role, positive/negative prompt, optional reference
 * image, size, and the generate action pinned to the bottom so it stays in
 * reach however long the prompt grows.
 */
export function PromptPanel({
  form,
  roles,
  settings,
  submitting,
  canSubmit,
  validationError,
  onChange,
  onPickBaseImage,
  onSubmit,
}: PromptPanelProps) {
  const [tab, setTab] = useState<PromptTab>("prompt");
  const roleOptions: SelectOption[] = roles.map((role) => ({ value: role.id, label: role.name, icon: <RoleAvatar role={role} /> }));
  // A dot on the negative tab says it carries text while the positive one is showing.
  const hasNegative = Boolean(form.negativePrompt.trim());
  const promptTabs = [
    { value: "prompt", label: "正向提示词" },
    { value: "negative", label: "负向提示词", badge: hasNegative ? <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" /> : undefined },
  ];

  return (
    <section className="surface-glass-strong grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden rounded-xl" data-testid="novelai-prompt-panel">
      <div className="scrollbar-stable grid min-h-0 content-start gap-4 overflow-y-auto p-4">
        <div className="flex min-w-0 items-center gap-2">
          <Select
            aria-label="生成角色"
            className={cx(inputClass, "h-10 min-w-0 flex-1 py-0 pl-2.5")}
            value={form.roleId}
            options={roleOptions}
            onValueChange={(roleId) => onChange({ roleId })}
          />
          <PromptSettingsPopover settings={settings} />
        </div>

        <div className="grid gap-2">
          <SegmentedControl ariaLabel="提示词类型" size="md" options={promptTabs} value={tab} onChange={(value) => setTab(value as PromptTab)} />
          <textarea
            className={cx(inputClass, "scrollbar-stable h-[clamp(132px,34vh,440px)] resize-none leading-relaxed")}
            aria-label={tab === "prompt" ? "正向提示词" : "负向提示词"}
            placeholder={tab === "prompt" ? "1girl, library, sunset light" : "lowres, bad hands, blurry"}
            value={tab === "prompt" ? form.prompt : form.negativePrompt}
            onChange={(event) => onChange(tab === "prompt" ? { prompt: event.target.value } : { negativePrompt: event.target.value })}
          />
        </div>

        <div className="grid gap-1.5">
          <span className={studioFieldLabelClass}>参考图</span>
          <BaseImageField form={form} onPick={onPickBaseImage} onChange={onChange} />
        </div>

        <SizeField form={form} validationError={validationError} onChange={onChange} />
      </div>

      <div className="border-t border-line-soft bg-white/50 p-4">
        <button
          className={cx(primaryButtonSurfaceClass, "flex h-11 w-full items-center justify-center gap-2 text-body font-medium")}
          type="button"
          disabled={!canSubmit}
          aria-busy={submitting}
          onClick={onSubmit}
        >
          <Sparkle className={cx("h-4 w-4", submitting && "nai-twinkle")} weight="fill" aria-hidden="true" />
          {submitting ? "生成中…" : "生成"}
        </button>
      </div>
    </section>
  );
}
