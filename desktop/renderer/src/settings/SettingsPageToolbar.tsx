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
        {subsections.length ? (
          <div className="relative max-w-full sm:max-w-[260px]">
            <select
              className="h-10 w-full appearance-none rounded-md border border-[#D8DCE2] bg-[#F3F5F7] px-3.5 pr-10 text-sm leading-5 text-[#1f1f1f] transition focus:border-[#D8DCE2] focus:outline-none focus-visible:border-[#D8DCE2] focus-visible:outline-none"
              value={currentSubsectionId ?? ""}
              onChange={(event) => onSubsectionChange(event.target.value)}
            >
              {subsections.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
              <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
                <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
              </svg>
            </span>
          </div>
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
