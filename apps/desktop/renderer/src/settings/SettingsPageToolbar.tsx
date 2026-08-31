import { ArrowCounterClockwise, FloppyDisk } from "@phosphor-icons/react";
import type { SettingsSubsection } from "./settingsSectionMetadata";
import type { SettingsSavePhase } from "./settingsPageTypes";
import { cx, panelTitleClass } from "../shared/styles";

type SettingsPageToolbarProps = {
  bridgeReady: boolean;
  currentSubsectionId: string | null;
  isDirty: boolean;
  savePhase: SettingsSavePhase;
  sectionLabel: string;
  subsections: SettingsSubsection[];
  onReset: () => void;
  onSave: () => Promise<void>;
  onSubsectionChange: (subsectionId: string) => void;
};

/** Renders the section header, subsection navigation, and the reset/save actions. */
export function SettingsPageToolbar({
  bridgeReady,
  currentSubsectionId,
  isDirty,
  savePhase,
  sectionLabel,
  subsections,
  onReset,
  onSave,
  onSubsectionChange,
}: SettingsPageToolbarProps) {
  const toolbarActionClass =
    "flex h-9 items-center gap-1.5 rounded-md border px-3.5 text-[13px] font-medium transition focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-default disabled:shadow-none";
  return (
    <div className="mx-auto flex w-full flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 flex-col gap-2.5">
        <h2 className={cx(panelTitleClass, "leading-none")}>{sectionLabel}</h2>
        {subsections.length > 1 ? (
          <nav className="scrollbar-soft flex max-w-full gap-1 overflow-x-auto" aria-label="设置子区">
            {subsections.map((item) => <button className={cx("h-8 shrink-0 rounded-md px-3 text-[13px] transition focus:outline-none focus:ring-2 focus:ring-primary/20", item.id === currentSubsectionId ? "bg-[rgba(202,93,46,0.09)] font-medium text-accent-deep" : "text-[#667085] hover:bg-[#F5F7FA] hover:text-[#182230]")} key={item.id} type="button" aria-current={item.id === currentSubsectionId ? "page" : undefined} onClick={() => onSubsectionChange(item.id)}>{item.label}</button>)}
          </nav>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          className={cx(
            toolbarActionClass,
            "border-stroke bg-white text-[#667085] hover:bg-[#F7F9FB] hover:text-[#182230] disabled:border-stroke disabled:bg-white disabled:text-[#b8b8b8]",
          )}
          type="button"
          aria-label="重置"
          onClick={onReset}
          disabled={!isDirty}
        >
          <ArrowCounterClockwise className="h-4 w-4" aria-hidden="true" />
          重置
        </button>
        <button
          className={cx(
            toolbarActionClass,
            "border-transparent bg-gradient-to-br from-primary to-[#e07b4d] text-white hover:opacity-90 disabled:border-transparent disabled:from-primary disabled:to-[#e07b4d] disabled:opacity-50",
          )}
          type="button"
          aria-label="保存并重启"
          onClick={() => void onSave()}
          disabled={!bridgeReady || !isDirty || savePhase === "saving"}
        >
          <FloppyDisk className="h-4 w-4" aria-hidden="true" />
          保存并重启
        </button>
      </div>
    </div>
  );
}
