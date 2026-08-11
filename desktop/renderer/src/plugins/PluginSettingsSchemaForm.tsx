import type { PluginSettingField, PluginSettingValue } from "../../../src/shared.js";
import { SettingsField } from "../settings/SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  SettingsToggleField,
  settingsInputClass,
} from "../settings/SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "../settings/settingsPageTypes";
import { readPluginSetting, writePluginSetting } from "./pluginSettingsSchema";

type PluginSettingsSchemaFormProps = SettingsSectionEditorProps & {
  schema: PluginSettingField[];
};

function inputValue(value: PluginSettingValue | undefined) {
  return value === undefined ? "" : String(value);
}

/** Renders a validated manifest settings schema against the shared settings draft. */
export function PluginSettingsSchemaForm({ draft, schema, updateDraft }: PluginSettingsSchemaFormProps) {
  function update(field: PluginSettingField, value: PluginSettingValue) {
    updateDraft((current) => writePluginSetting(current, field.config_path, value));
  }

  return (
    <SettingsSectionCard>
      {schema.map((field) => {
        const value = readPluginSetting(draft, field.config_path);
        if (value === undefined) return null;
        if (field.type === "boolean") {
          return <SettingsToggleField key={field.id} label={field.label} hint={field.hint} checked={Boolean(value)} onChange={(checked) => update(field, checked)} />;
        }
        return (
          <SettingsField key={field.id} label={field.label} hint={field.hint}>
            {field.type === "secret" ? (
              <SettingsSecretInput value={inputValue(value)} onChange={(next) => update(field, next)} />
            ) : field.type === "select" ? (
              <select className={settingsInputClass} value={inputValue(value)} onChange={(event) => {
                const option = field.options?.find((item) => String(item.value) === event.target.value);
                if (option) update(field, option.value);
              }}>
                {field.options?.map((option) => <option key={String(option.value)} value={String(option.value)}>{option.label}</option>)}
              </select>
            ) : (
              <input
                className={settingsInputClass}
                type={field.type === "number" ? "number" : "text"}
                value={inputValue(value)}
                onChange={(event) => {
                  if (field.type !== "number") {
                    update(field, event.target.value);
                    return;
                  }
                  const next = Number(event.target.value);
                  if (Number.isFinite(next)) update(field, next);
                }}
              />
            )}
          </SettingsField>
        );
      })}
    </SettingsSectionCard>
  );
}
