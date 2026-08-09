import type { SettingsSubsection } from "./settingsSectionMetadata";
import type { SettingsSavePhase } from "./settingsPageTypes";
import { ResetIcon, SaveIcon } from "../shared/icons";
import { cx } from "../shared/styles";

type SettingsPageToolbarProps = {
  bridgeReady: boolean;
  currentSubsectionId: string | null;
  isDirty: boolean;
  savePhase: SettingsSavePhase;
  subsections: SettingsSubsection[];
  onReset: () => void;
  onSave: () => Promise<void>;
  onSubsectionChange: (subsectionId: string) => void;
};

/** Renders subsection navigation and the reset/save actions. */
export function SettingsPageToolbar({
  bridgeReady,
  currentSubsectionId,
  isDirty,
  savePhase,
  subsections,
  onReset,
  onSave,
  onSubsectionChange,
}: SettingsPageToolbarProps) {
  const floatingActionClass =
    "grid h-10 w-10 place-items-center rounded-full border bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none";
  return (
    <div className="mx-auto flex w-full flex-col gap-4 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        {subsections.length > 1 ? (
          <nav className="scrollbar-soft flex max-w-full gap-1 overflow-x-auto" aria-label="设置子区">
            {subsections.map((item) => <button className={cx("h-9 shrink-0 rounded-md px-3 text-sm transition focus:outline-none focus:ring-2 focus:ring-primary/20", item.id === currentSubsectionId ? "bg-[#EEF4FA] font-medium text-[#1D5F9E]" : "text-[#667085] hover:bg-[#F5F7FA] hover:text-[#182230]")} key={item.id} type="button" aria-current={item.id === currentSubsectionId ? "page" : undefined} onClick={() => onSubsectionChange(item.id)}>{item.label}</button>)}
          </nav>
        ) : null}
      </div>
      <div className="flex items-center gap-2.5">
        <button
          className={cx(floatingActionClass, "border-black/8 text-[#747474] hover:border-black/14 hover:bg-[#F5F7FA] hover:text-[#4f4f4f]")}
          type="button"
          aria-label="重置"
          onClick={onReset}
          disabled={!isDirty}
        >
          <ResetIcon className="h-[18px] w-[18px] fill-current" />
        </button>
        <button
          className={cx(floatingActionClass, "border-transparent bg-white text-[#1f1f1f] hover:bg-[#F5F7FA]")}
          type="button"
          aria-label="保存并重启"
          onClick={() => void onSave()}
          disabled={!bridgeReady || !isDirty || savePhase === "saving"}
        >
          <SaveIcon className="h-[18px] w-[18px] fill-current" />
        </button>
      </div>
    </div>
  );
}
