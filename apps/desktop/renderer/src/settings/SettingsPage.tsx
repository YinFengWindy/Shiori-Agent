import { useEffect } from "react";
import { pluginUiRegistry, type EditorSettingsSectionEntry } from "../plugins/pluginUiRegistry";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback";
import { SettingsSavedIndicator } from "./SettingsSavedIndicator";
import { SettingsPageLayout, settingsPageSurfaceClass } from "./SettingsPageLayout";
import { SettingsSectionContent } from "./SettingsSectionContent";
import { SettingsSubsectionNav } from "./SettingsSubsectionNav";
import type { SettingsSectionId } from "./SettingsSidebar";
import { getSettingsSubsections, resolveSettingsSubsectionId } from "./settingsSectionMetadata";
import type { SettingsSubsection } from "./settingsPageTypes";
import { useSettingsPageController } from "./useSettingsPageController";
import { cardClass, cx } from "../shared/styles";

type SettingsPageProps = {
  bridgeReady: boolean;
  section: SettingsSectionId;
  /** Hides a plugin's section immediately once its plugin is disabled (issue #174 AC 3). */
  isSectionVisible: (sectionId: SettingsSectionId) => boolean;
  /** Filters a plugin-owned subtab the same way (issue #230 AC 3). */
  isPluginEnabled: (pluginId: string) => boolean;
  /**
   * The last active subtab per section id, lifted to the app shell (issue
   * #230 AC 4) so it survives switching between sections — including
   * between an "editor" section and a "standalone" one like 「插件」, which
   * unmounts this component's own internal state on every switch. Owned by
   * `useSettingsSubsectionMemory`; this component only reads it and calls
   * `onChangeSubsection` to write through it.
   */
  activeSubsections: Record<string, string>;
  onChangeSubsection: (sectionId: string, subsectionId: string) => void;
};

/**
 * Renders the active settings domain and delegates persistence to its
 * controller. A "standalone" section (About, and 「插件」's own subtabs —
 * each owns its data end to end) renders immediately, without waiting on or
 * depending on the shared settings draft; an "editor" section shares the
 * draft/autosave controller mounted below. Both branches render through the
 * same `SettingsSubsectionNav` header/subtab strip, so a standalone section
 * with more than one subtab (「插件」, once a plugin's settings nest under
 * it) gets the same navigation an editor section already had.
 */
export function SettingsPage({
  bridgeReady,
  section,
  isSectionVisible,
  isPluginEnabled,
  activeSubsections,
  onChangeSubsection,
}: SettingsPageProps) {
  const entry = isSectionVisible(section) ? pluginUiRegistry.getSettingsSection(section) : undefined;
  const visibleSubsections = entry ? getSettingsSubsections(entry.id, isPluginEnabled) : [];
  const currentSubsectionId = entry ? resolveSettingsSubsectionId(entry.id, activeSubsections, isPluginEnabled) : null;

  // Issue #230 AC 3's fallback commit. `useSettingsSubsectionMemory`'s doc
  // comment explains why resolving alone is not enough; this is the caller
  // half it names, because only this component knows the rendered section
  // and its live `isPluginEnabled` filter. Equality-guarded, so it fires
  // only when the resolved answer actually disagrees with the record.
  useEffect(() => {
    if (!entry || !currentSubsectionId) return;
    if (activeSubsections[entry.id] !== currentSubsectionId) {
      onChangeSubsection(entry.id, currentSubsectionId);
    }
  }, [entry, currentSubsectionId, activeSubsections, onChangeSubsection]);

  if (entry?.kind === "standalone") {
    // A subtab nested under this section (a plugin's own settings, issue
    // #230) renders its own Component; the section's own Component only
    // ever backs its own built-in subtab(s) (e.g. 「插件」's "已安装", or
    // "关于"'s single "updates" subtab).
    const nested = currentSubsectionId ? pluginUiRegistry.getSettingsSubsection(entry.id, currentSubsectionId) : undefined;
    const StandaloneComponent = nested?.Component ?? entry.Component;
    return (
      <SettingsPageLayout>
        <SettingsSubsectionNav
          label={entry.label}
          subsections={visibleSubsections}
          currentSubsectionId={currentSubsectionId}
          onSelect={(id) => onChangeSubsection(entry.id, id)}
        />
        {currentSubsectionId ? <StandaloneComponent subsectionId={currentSubsectionId} /> : null}
      </SettingsPageLayout>
    );
  }
  return (
    <EditableSettingsPage
      bridgeReady={bridgeReady}
      currentSectionEntry={entry}
      visibleSubsections={visibleSubsections}
      currentSubsectionId={currentSubsectionId}
      onChangeSubsection={onChangeSubsection}
    />
  );
}

type EditableSettingsPageProps = {
  bridgeReady: boolean;
  currentSectionEntry: EditorSettingsSectionEntry | undefined;
  visibleSubsections: SettingsSubsection[];
  currentSubsectionId: string | null;
  onChangeSubsection: (sectionId: string, subsectionId: string) => void;
};

function EditableSettingsPage({
  bridgeReady,
  currentSectionEntry,
  visibleSubsections,
  currentSubsectionId,
  onChangeSubsection,
}: EditableSettingsPageProps) {
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

  return (
    <SettingsPageLayout
      status={<SettingsSavedIndicator phase={controller.savePhase} />}
      feedback={
        <SettingsSaveFeedback
          phase={controller.savePhase}
          message={controller.statusMessage}
          onRetry={controller.retrySave}
          onReload={controller.reloadSettings}
        />
      }
    >
      {!currentSectionEntry ? (
        <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-ink-muted")}>
          没有匹配的设置项
        </div>
      ) : (
        <SettingsSubsectionNav
          label={currentSectionEntry.label}
          subsections={visibleSubsections}
          currentSubsectionId={currentSubsectionId}
          onSelect={(id) => onChangeSubsection(currentSectionEntry.id, id)}
        />
      )}
      {currentSectionEntry && currentSubsectionId ? (
        <SettingsSectionContent
          sectionId={currentSectionEntry.id}
          subsectionId={currentSubsectionId}
          draft={controller.draft}
          updateDraft={controller.updateDraft}
        />
      ) : null}
    </SettingsPageLayout>
  );
}
