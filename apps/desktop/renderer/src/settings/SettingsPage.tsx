import { Suspense, useEffect } from "react";
import { pluginUiRegistry, type EditorSettingsSectionEntry, type StandaloneSettingsSectionEntry } from "../plugins/pluginUiRegistry";
import { SettingsSaveFeedback } from "./SettingsSaveFeedback";
import { SettingsSavedIndicator } from "./SettingsSavedIndicator";
import { SettingsPageLayout, settingsPageSurfaceClass } from "./SettingsPageLayout";
import { SettingsSectionContent } from "./SettingsSectionContent";
import { SettingsStatus } from "./SettingsStatusSlot";
import { SettingsSubsectionNav } from "./SettingsSubsectionNav";
import type { SettingsSectionId } from "./SettingsSidebar";
import { resolveSettingsSubsectionId } from "./settingsSectionMetadata";
import type { SettingsSubsection } from "./settingsPageTypes";
import { useSettingsPageController } from "./useSettingsPageController";
import { cardClass, cx } from "../shared/styles";
import { InlineError } from "../shared/feedback/InlineError";
import { PluginAccountsSection } from "../accounts/PluginAccountsSection";

type SettingsPageProps = {
  bridgeReady: boolean;
  section: SettingsSectionId;
  /** Hides a plugin's section immediately once its plugin is disabled (issue #174 AC 3). */
  isSectionVisible: (sectionId: SettingsSectionId) => boolean;
  /** Filters a plugin-owned nested page the same way (issue #230 AC 3). */
  isPluginEnabled: (pluginId: string) => boolean;
  /**
   * The last active subsection per section id, lifted to the app shell (issue
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
 * controller. A "standalone" section (About, 外观, 「插件」 — each owns its
 * data end to end) renders immediately, without waiting on or depending on
 * the shared settings draft; an "editor" section shares the draft/autosave
 * controller mounted below. Both branches render through the same
 * `SettingsSubsectionNav` header, whose tab strip lists a section's own
 * declared subsections.
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
    return (
      <StandaloneSettingsPage
        entry={entry}
        currentSubsectionId={currentSubsectionId}
        onSelect={(id) => onChangeSubsection(entry.id, id)}
      />
    );
  }
  return (
    <EditableSettingsPage
      bridgeReady={bridgeReady}
      currentSectionEntry={entry}
      visibleSubsections={entry?.subsections ?? []}
      currentSubsectionId={currentSubsectionId}
      onChangeSubsection={onChangeSubsection}
    />
  );
}

/**
 * A nested subsection (a plugin's own settings, issue #230) is a detail page
 * reached from the section's own list — never a tab beside it — so its
 * header carries a way back instead of the section's tab strip.
 */
function StandaloneSettingsPage({ entry, currentSubsectionId, onSelect }: {
  entry: StandaloneSettingsSectionEntry;
  currentSubsectionId: string | null;
  onSelect: (subsectionId: string) => void;
}) {
  const nested = currentSubsectionId ? pluginUiRegistry.getSettingsSubsection(entry.id, currentSubsectionId) : undefined;
  const home = entry.subsections[0]?.id;
  if (nested) {
    const NestedComponent = nested.Component;
    return (
      <SettingsPageLayout>
        <SettingsSubsectionNav
          label={nested.label}
          subsections={[]}
          currentSubsectionId={nested.id}
          onSelect={onSelect}
          back={home ? { label: entry.label, onBack: () => onSelect(home) } : undefined}
        />
        {/* Schema-generated plugin pages load on first open (see pluginSchemaSettingsSectionFactory). */}
        <Suspense fallback={null}>
          <div className="grid gap-6">
            {nested.pluginId ? <PluginAccountsSection pluginId={nested.pluginId} /> : null}
            <NestedComponent key={nested.id} subsectionId={nested.id} onSelectSubsection={onSelect} />
          </div>
        </Suspense>
      </SettingsPageLayout>
    );
  }
  const SectionComponent = entry.Component;
  return (
    <SettingsPageLayout>
      <SettingsSubsectionNav
        label={entry.label}
        subsections={entry.subsections}
        currentSubsectionId={currentSubsectionId}
        onSelect={onSelect}
      />
      {currentSubsectionId ? <SectionComponent subsectionId={currentSubsectionId} onSelectSubsection={onSelect} /> : null}
    </SettingsPageLayout>
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
        <InlineError layout="card" className="mx-8" persona="settingsLoadFailed" title="设置加载失败" message={controller.loadError} />
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
      feedback={
        <SettingsSaveFeedback
          phase={controller.savePhase}
          message={controller.statusMessage}
          onRetry={controller.retrySave}
          onReload={controller.reloadSettings}
        />
      }
    >
      <SettingsStatus><SettingsSavedIndicator phase={controller.savePhase} /></SettingsStatus>
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
