import { useEffect, useRef, useState } from "react";
import { SettingsField } from "../settings/SettingsField";
import {
  SettingsNumberInput,
  SettingsSecretInput,
  SettingsToggleField,
  settingsInputClass,
} from "../settings/SettingsFieldPrimitives";
import { SettingsStringListInput } from "../settings/SettingsStringListInput";
import { cx, textareaClass } from "../shared/styles";
import { Select } from "../shared/ui/Select";
import { readStringList, type PluginConfigField } from "./jsonSchemaForm";
import { PluginEnvReferenceInput } from "./PluginEnvReferenceInput";

type FieldRowProps = {
  field: PluginConfigField;
  value: unknown;
  onChange: (value: unknown) => void;
};

/**
 * Renders one field with the control its schema shape calls for.
 * `envResolved` says whether the stored `${NAME}` reference, if any, resolves
 * in Shiori's environment (from `plugin.config.get`'s `env_status`).
 */
export function PluginConfigFieldRow({ field, value, envResolved, onChange }: FieldRowProps & { envResolved: boolean }) {
  switch (field.kind) {
    case "boolean":
      return <SettingsToggleField label={field.label} hint={field.hint} checked={Boolean(value)} onChange={onChange} />;
    case "enum":
      return (
        <SettingsField label={field.label} hint={field.hint}>
          <Select
            aria-label={field.label}
            className={settingsInputClass}
            value={String(value ?? "")}
            onValueChange={onChange}
            options={(field.options ?? []).map((option) => ({ value: option, label: option }))}
          />
        </SettingsField>
      );
    case "secret":
      return (
        <SettingsField label={field.label} hint={field.hint}>
          <PluginEnvReferenceInput
            value={value}
            label={field.label}
            resolved={envResolved}
            renderInput={(displayValue, onBlurEmpty) => (
              <SettingsSecretInput
                value={displayValue}
                onChange={onChange}
                ariaLabel={field.label}
                autoFocus={displayValue !== String(value ?? "")}
                onBlur={() => { if (!displayValue) onBlurEmpty(); }}
              />
            )}
          />
        </SettingsField>
      );
    case "number":
    case "integer":
      return (
        <SettingsField label={field.label} hint={field.hint}>
          <SettingsNumberInput ariaLabel={field.label} unit={field.unit} min={field.min} max={field.max} value={Number(value ?? 0)} onChange={onChange} />
        </SettingsField>
      );
    case "stringList":
      return (
        <SettingsField label={field.label} hint={field.hint}>
          <SettingsStringListInput ariaLabel={field.label} items={readStringList(value)} onChange={onChange} />
        </SettingsField>
      );
    case "json":
      return <JsonFieldRow field={field} value={value} onChange={onChange} />;
    case "string":
      return (
        <SettingsField label={field.label} hint={field.hint}>
          <PluginEnvReferenceInput
            value={value}
            label={field.label}
            resolved={envResolved}
            renderInput={(displayValue, onBlurEmpty) => (
              <input
                aria-label={field.label}
                className={settingsInputClass}
                autoFocus={displayValue !== String(value ?? "")}
                value={displayValue}
                onBlur={() => { if (!displayValue) onBlurEmpty(); }}
                onChange={(event) => onChange(event.target.value)}
              />
            )}
          />
        </SettingsField>
      );
  }
}

/**
 * Raw JSON editor for fields whose shape (object, list of objects, $ref) has
 * no dedicated control. Resyncs its text from `value` whenever that value
 * changed for a reason other than this field's own last edit (e.g.
 * `reloadConfig` replacing the whole draft) — otherwise a reload after this
 * field mounted would leave the textarea showing stale content.
 */
function JsonFieldRow({ field, value, onChange }: FieldRowProps) {
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [invalid, setInvalid] = useState(false);
  const pendingLocalEditRef = useRef(false);

  useEffect(() => {
    if (pendingLocalEditRef.current) {
      pendingLocalEditRef.current = false;
      return;
    }
    setText(JSON.stringify(value ?? null, null, 2));
    setInvalid(false);
  }, [value]);

  return (
    <SettingsField label={field.label} hint={field.hint} layout="stack">
      <textarea
        aria-label={field.label}
        className={cx(textareaClass, "font-mono text-body-sm", invalid && "border-danger")}
        value={text}
        onChange={(event) => {
          const nextText = event.target.value;
          setText(nextText);
          try {
            const parsed = JSON.parse(nextText);
            pendingLocalEditRef.current = true;
            onChange(parsed);
            setInvalid(false);
          } catch {
            setInvalid(true);
          }
        }}
      />
      {invalid ? <p className="mt-1 text-caption text-danger-text">JSON 格式无效</p> : null}
    </SettingsField>
  );
}
