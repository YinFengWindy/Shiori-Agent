import { useDeferredValue, useState } from "react";
import { SettingsPageToolbar } from "./SettingsPageToolbar";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback";
import { SettingsSectionContent } from "./SettingsSectionContent";
import { type SettingsSectionId, settingsSections } from "./SettingsSidebar";
import {
  createInitialSettingsSubsectionState,
  resolveSettingsSubsectionId,
  settingsSubsections,
} from "./settingsSectionMetadata";
import { useSettingsPageController } from "./useSettingsPageController";
import { cardClass, cx } from "../shared/styles";

type SettingsPageProps = {
  bridgeReady: boolean;
  search: string;
  section: SettingsSectionId;
  onMetaChange?: (meta: { configPath: string; dirty: boolean }) => void;
};

/** Shared surface style for every settings page state. */
export const settingsPageSurfaceClass = "settings-page bg-white";

/** Responsive spacing for the settings toolbar. */
export const settingsToolbarClass = "border-b border-[#E8EBF0] bg-white px-3 py-3 sm:px-5 lg:px-7";

/** Responsive spacing for the scrollable settings content. */
export const settingsContentClass = "relative scrollbar-soft overflow-y-auto bg-white px-3 py-5 sm:px-5 lg:px-7 lg:py-7";

/** Renders the active settings domain and delegates persistence to its controller. */
export function SettingsPage({ bridgeReady, search, section, onMetaChange }: SettingsPageProps) {
  const [activeSubsections, setActiveSubsections] = useState<Record<SettingsSectionId, string>>(
    createInitialSettingsSubsectionState,
  );
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const controller = useSettingsPageController({ bridgeReady, onMetaChange });

  if (controller.loadError) {
    return (
      <section className={cx(settingsPageSurfaceClass, "grid h-full place-items-center")} data-testid="settings-page">
        <div className={cx(cardClass, "mx-8 max-w-[680px] p-6 text-sm leading-6 text-[#8f2d2d]")}>
          设置加载失败：{controller.loadError}
        </div>
      </section>
    );
  }

  if (!controller.draft) {
    return (
      <section className={cx(settingsPageSurfaceClass, "grid h-full place-items-center")} data-testid="settings-page">
        <div className="text-sm text-[#737781]">正在加载设置...</div>
      </section>
    );
  }

  const visibleSections = settingsSections.filter((item) => (
    !deferredSearch
    || item.label.toLowerCase().includes(deferredSearch)
    || item.id.toLowerCase().includes(deferredSearch)
  ));
  const currentSection = visibleSections.find((item) => item.id === section)
    ?? visibleSections[0]
    ?? null;
  const currentId = currentSection?.id ?? null;
  const visibleSubsections = currentId ? settingsSubsections[currentId] : [];
  const currentSubsectionId = currentId
    ? resolveSettingsSubsectionId(currentId, activeSubsections)
    : null;

  function updateActiveSubsection(nextId: string): void {
    if (!currentId) return;
    setActiveSubsections((current) => (
      current[currentId] === nextId
        ? current
        : { ...current, [currentId]: nextId }
    ));
  }

  return (
    <section className={cx(settingsPageSurfaceClass, "relative grid h-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden")} data-testid="settings-page">
      <SettingsSaveFeedback
        phase={controller.savePhase}
        message={controller.statusMessage}
      />
      <div className="settings-content grid min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
        <div className={settingsToolbarClass}>
          <SettingsPageToolbar
            bridgeReady={bridgeReady}
            currentSubsectionId={currentSubsectionId}
            isDirty={controller.isDirty}
            savePhase={controller.savePhase}
            subsections={visibleSubsections}
            onReset={controller.reset}
            onSave={controller.save}
            onSubsectionChange={updateActiveSubsection}
          />
        </div>
        <div className={settingsContentClass}>
          <div className="mx-auto w-full max-w-none">
            {!currentSection ? (
              <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
                没有匹配的设置项
              </div>
            ) : null}
            {currentId && currentSubsectionId ? (
              <SettingsSectionContent
                sectionId={currentId}
                subsectionId={currentSubsectionId}
                draft={controller.draft}
                updateDraft={controller.updateDraft}
              />
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
