import { useState } from "react";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback";
import { SettingsPageLayout, settingsPageSurfaceClass } from "./SettingsPageLayout";
import { SettingsSectionContent } from "./SettingsSectionContent";
import type { SettingsSectionId } from "./SettingsSidebar";
import {
  createInitialSettingsSubsectionState,
  getSettingsSubsections,
  resolveSettingsSubsectionId,
} from "./settingsSectionMetadata";
import { useSettingsPageController } from "./useSettingsPageController";
import { cardClass, cx } from "../shared/styles";

type SettingsPageProps = {
  bridgeReady: boolean;
  section: SettingsSectionId;
  /** Hides a plugin's section immediately once its plugin is disabled (issue #174 AC 3). */
  isSectionVisible?: (sectionId: SettingsSectionId) => boolean;
};

/**
 * Renders the active settings domain and delegates persistence to its
 * controller. A "standalone" section (About, and any plugin-contributed
 * settings.section — both own their data end to end) renders immediately,
 * without waiting on or depending on the shared settings draft; an
 * "editor" section shares the draft/autosave controller mounted below.
 */
export function SettingsPage({
  bridgeReady,
  section,
  isSectionVisible = () => true,
}: SettingsPageProps) {
  const entry = isSectionVisible(section) ? pluginUiRegistry.getSettingsSection(section) : undefined;
  if (entry?.kind === "standalone") {
    const StandaloneComponent = entry.Component;
    const subsectionId = entry.subsections[0]?.id ?? "";
    return (
      <SettingsPageLayout>
        <StandaloneComponent subsectionId={subsectionId} />
      </SettingsPageLayout>
    );
  }
  return <EditableSettingsPage bridgeReady={bridgeReady} section={section} isSectionVisible={isSectionVisible} />;
}

function EditableSettingsPage({
  bridgeReady,
  section,
  isSectionVisible = () => true,
}: SettingsPageProps) {
  const [activeSubsections, setActiveSubsections] = useState<Record<string, string>>(
    createInitialSettingsSubsectionState,
  );
  const controller = useSettingsPageController({ bridgeReady });

  if (controller.loadError) {
    return (
      <section className={cx(settingsPageSurfaceClass, "grid h-full place-items-center")} data-testid="settings-page">
        <div className={cx(cardClass, "mx-8 max-w-[680px] p-6 text-sm leading-6 text-danger-text")}>
          设置加载失败：{controller.loadError}
        </div>
      </section>
    );
  }

  if (!controller.draft) {
    return (
      <section className={cx(settingsPageSurfaceClass, "grid h-full place-items-center")} data-testid="settings-page">
        <div className="text-sm text-ink-muted">正在加载设置…</div>
      </section>
    );
  }

  const currentSection = isSectionVisible(section) ? pluginUiRegistry.getSettingsSection(section) : undefined;
  const currentId = currentSection?.id ?? null;
  const visibleSubsections = currentId ? getSettingsSubsections(currentId) : [];
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
    <SettingsPageLayout
      feedback={
        <SettingsSaveFeedback
          phase={controller.savePhase}
          message={controller.statusMessage}
          onRetry={controller.retrySave}
          onReload={controller.reloadSettings}
        />
      }
    >
      {!currentSection ? (
        <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-ink-muted")}>
          没有匹配的设置项
        </div>
      ) : (
        <header className="mb-6">
          <h2 className="m-0 font-display text-headline text-ink">{currentSection.label}</h2>
          {visibleSubsections.length > 1 ? (
            <nav className="mt-7 flex max-w-full gap-7 overflow-x-auto" aria-label="设置子区">
              {visibleSubsections.map((item) => (
                <button
                  className={cx(
                    "relative shrink-0 border-0 bg-transparent px-0 pb-2 text-[13px] transition focus:outline-none",
                    item.id === currentSubsectionId
                      ? "font-medium text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-accent"
                      : "text-ink-faint hover:text-ink-secondary",
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
    </SettingsPageLayout>
  );
}
