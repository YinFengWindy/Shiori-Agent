import type React from "react";
import { SettingsSectionIntro } from "./settingsUi";
import { buildSettingsSectionIntro } from "./settingsMetadata";
import { renderPrioritySettingsSection } from "./SettingsPrioritySections";
import { renderSupportSettingsSection } from "./SettingsSupportSections";
import type { SettingsSectionContentProps } from "./settingsSectionTypes";

/** Dispatches the active settings section to the corresponding renderer and prepends the shared intro block. */
export function SettingsSectionContent(props: SettingsSectionContentProps): React.ReactNode {
  const intro = buildSettingsSectionIntro(
    props.section,
    props.subsectionId,
    props.draft,
    props.roles,
    props.dirty,
  );

  const content = props.section === "models" || props.section === "proactive" || props.section === "integrations"
    ? renderPrioritySettingsSection(props)
    : renderSupportSettingsSection(props);

  return (
    <div className="grid gap-6">
      <SettingsSectionIntro title={intro.title} summary={intro.summary} statuses={intro.statuses} />
      {content}
    </div>
  );
}
