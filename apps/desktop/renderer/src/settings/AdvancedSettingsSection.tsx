import { SettingsField as Field } from "./SettingsField";
import { SettingsGroup, SettingsNumberInput, SettingsToggleField, settingsGroupStackClass } from "./SettingsFieldPrimitives";
import { advancedSettingsGroups, type AdvancedSettingsField } from "./advancedSettingsFields";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

/** Renders advanced runtime settings, grouped by topic with each raw config key beside its label. */
export function AdvancedSettingsSection({
  draft,
  subsectionId,
  updateDraft,
}: SettingsSectionEditorProps) {
  if (subsectionId !== "general") return null;
  const setAdvanced = (patch: Partial<SettingsSectionEditorProps["draft"]["advanced"]>) => updateDraft((current) => ({
    ...current,
    advanced: { ...current.advanced, ...patch },
  }));
  const renderField = (field: AdvancedSettingsField) => field.kind === "number" ? (
    <Field key={field.key} label={field.label} configKey={field.configKey}>
      <SettingsNumberInput
        ariaLabel={field.label}
        unit={field.unit}
        value={draft.advanced[field.key]}
        onChange={(value) => setAdvanced({ [field.key]: value })}
      />
    </Field>
  ) : (
    <SettingsToggleField
      key={field.key}
      label={field.label}
      configKey={field.configKey}
      checked={Boolean(draft.advanced[field.key])}
      onChange={(checked) => setAdvanced({ [field.key]: checked })}
    />
  );
  return (
    <div className={settingsGroupStackClass}>
      {advancedSettingsGroups.map((group) => (
        <SettingsGroup key={group.title} title={group.title}>
          {group.fields.map(renderField)}
        </SettingsGroup>
      ))}
    </div>
  );
}
