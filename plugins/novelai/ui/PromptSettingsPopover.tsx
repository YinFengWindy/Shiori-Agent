import { useEffect, useId, useRef, useState } from "react";
import { SlidersHorizontal } from "@phosphor-icons/react";
import { SettingsToggleCard } from "../../../apps/desktop/renderer/src/settings/SettingsToggleCard";
import { cx, iconButtonClass } from "../../../apps/desktop/renderer/src/shared/styles";
import { menuPanelClass, menuSeparatorClass } from "../../../apps/desktop/renderer/src/shared/ui/Menu";
import { SegmentedControl } from "./SegmentedControl";
import { undesiredContentPresetOptions } from "./studioForm";
import type { NovelAiPromptSettings } from "./useNovelAiPromptSettings";

type PromptSettingsPopoverProps = {
  settings: NovelAiPromptSettings;
};

/**
 * The prompt switches that are plugin config (NSFW, quality tags,
 * undesired-content preset) behind one icon button; changes autosave through
 * the plugin config controller. Hand-rolled (enter-only motion, closes on an
 * outside press or Escape) because Base UI is not resolvable from plugin
 * code; the preset is a segmented control so nothing inside opens a portal.
 */
export function PromptSettingsPopover({ settings }: PromptSettingsPopoverProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return undefined;
    function handlePointerDown(event: PointerEvent): void {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="relative shrink-0" ref={rootRef}>
      <button
        className={cx(iconButtonClass, open && "border-line-accent bg-accent-softer text-accent-text")}
        type="button"
        aria-label="生成设置"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        data-testid="novelai-prompt-settings"
        onClick={() => setOpen((current) => !current)}
      >
        <SlidersHorizontal className="h-[18px] w-[18px]" aria-hidden="true" />
      </button>
      {open ? (
        <div
          id={panelId}
          className={cx(menuPanelClass, "motion-popover-enter absolute right-0 top-[calc(100%+6px)] z-30 grid w-72 origin-top-right gap-3 p-3")}
          role="dialog"
          aria-label="生成设置"
        >
          <div className="flex items-center justify-between gap-3 text-body-sm text-ink-secondary">
            <span>NSFW 模式</span>
            <SettingsToggleCard compact checked={settings.nsfwEnabled} ariaLabel="NSFW 模式" onChange={settings.setNsfwEnabled} />
          </div>
          <div className="flex items-center justify-between gap-3 text-body-sm text-ink-secondary">
            <span>自动添加质量标签</span>
            <SettingsToggleCard compact checked={settings.addQualityTags} ariaLabel="自动添加质量标签" onChange={settings.setAddQualityTags} />
          </div>
          <div className="grid gap-1.5 text-body-sm text-ink-secondary">
            <span>负向预设</span>
            <SegmentedControl
              ariaLabel="负向预设"
              options={undesiredContentPresetOptions}
              value={String(settings.undesiredContentPreset)}
              onChange={(value) => settings.setUndesiredContentPreset(Number(value))}
            />
          </div>
          <div className={menuSeparatorClass} role="separator" />
          <div className="grid gap-0.5">
            <span className="text-caption text-ink-muted">模型</span>
            <span className="truncate font-mono text-caption text-ink-secondary" title={settings.model}>{settings.model}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
