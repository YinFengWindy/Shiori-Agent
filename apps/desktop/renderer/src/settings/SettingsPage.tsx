import { useState } from "react";
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
  section: SettingsSectionId;
};

/** Shared surface style for every settings page state. */
export const settingsPageSurfaceClass = "settings-page bg-white";

/** Responsive spacing for the scrollable settings content. */
export const settingsContentClass = "relative scrollbar-soft overflow-y-auto bg-white px-4 py-8 sm:px-10 lg:px-16 lg:py-10";

/** Renders the active settings domain and delegates persistence to its controller. */
export function SettingsPage({
  bridgeReady,
  section,
}: SettingsPageProps) {
  const [activeSubsections, setActiveSubsections] = useState<Record<SettingsSectionId, string>>(
    createInitialSettingsSubsectionState,
  );
  const controller = useSettingsPageController({ bridgeReady });

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

  const currentSection = settingsSections.find((item) => item.id === section) ?? settingsSections[0] ?? null;
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
    <section className={cx(settingsPageSurfaceClass, "relative grid h-full grid-rows-[minmax(0,1fr)] overflow-hidden")} data-testid="settings-page">
      <SettingsSaveFeedback
        phase={controller.savePhase}
        message={controller.statusMessage}
      />
      <div className={settingsContentClass}>
        <div className="mx-auto w-full max-w-[840px]">
          {!currentSection ? (
            <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
              没有匹配的设置项
            </div>
          ) : (
            <header className="mb-6">
              <h2 className="m-0 text-[22px] font-normal leading-tight text-[#182230]">{currentSection.label}</h2>
              {visibleSubsections.length > 1 ? (
                <nav className="mt-7 flex max-w-full gap-7 overflow-x-auto" aria-label="设置子区">
                  {visibleSubsections.map((item) => (
                    <button
                      className={cx(
                        "relative shrink-0 border-0 bg-transparent px-0 pb-2 text-[13px] transition focus:outline-none",
                        item.id === currentSubsectionId
                          ? "font-medium text-[#182230] after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-[#182230]"
                          : "text-[#98A2B3] hover:text-[#3a4453]",
                      )}
                      key={item.id}
                      type="button"
                      aria-current={item.id === currentSubsectionId ? "page" : undefined}
                      onClick={() => updateActiveSubsection(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </nav>
              ) : null}
            </header>
          )}
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
    </section>
  );
}
