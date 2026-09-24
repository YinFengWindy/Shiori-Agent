import { useState } from "react";
import { Select } from "../shared/ui/Select";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortOptions } from "../shared/modelEffortLabels";
import { SettingsField as Field } from "./SettingsField";
import { SettingsSecretInput, settingsInputClass } from "./SettingsFieldPrimitives";
import { ModelConnectionTestAction } from "./ModelConnectionTestAction";
import { applyProviderPreset, customProviderPresetId, findProviderPreset, modelProviderOptions } from "./modelProviderPresets";

/** Model registration fields shared by the catalog and first-run setup. */
export function ModelRegistrationFields({ registration, onChange }: {
  registration: ModelRegistrationFormData;
  onChange: (mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData) => void;
}) {
  const inputClass = settingsInputClass;
  // 「自定义」 chosen explicitly stays selected even while the values still equal a preset.
  const [customFor, setCustomFor] = useState<string | null>(null);
  const preset = customFor === registration.id ? undefined : findProviderPreset(registration);
  const choosePreset = (value: string) => {
    if (value === customProviderPresetId) {
      setCustomFor(registration.id);
      return;
    }
    setCustomFor(null);
    onChange((current) => applyProviderPreset(current, value));
  };
  return (
    <div className="grid">
      <Field label="服务商">
        <Select aria-label="服务商" className={inputClass} value={preset?.id ?? customProviderPresetId} onValueChange={choosePreset} options={modelProviderOptions} />
      </Field>
      {preset ? null : (
        <Field label="服务商标识">
          <input aria-label="服务商标识" className={inputClass} placeholder="openai" value={registration.provider} onChange={(event) => onChange((current) => ({ ...current, provider: event.target.value }))} />
        </Field>
      )}
      <Field label="Base URL">
        <input aria-label="Base URL" className={inputClass} placeholder="https://example.com/v1" value={registration.baseUrl} onChange={(event) => onChange((current) => ({ ...current, baseUrl: event.target.value }))} />
      </Field>
      <Field label="API Key">
        <SettingsSecretInput ariaLabel="API Key" value={registration.apiKey} onChange={(value) => onChange((current) => ({ ...current, apiKey: value }))} />
      </Field>
      <Field label="模型">
        <input aria-label="模型" className={inputClass} placeholder={preset?.modelHint} value={registration.model} onChange={(event) => onChange((current) => ({ ...current, model: event.target.value }))} />
      </Field>
      <Field label="思考强度">
        <Select aria-label="思考强度" className={inputClass} value={registration.effort} onValueChange={(value) => onChange((current) => ({ ...current, effort: value as ModelRegistrationFormData["effort"] }))} options={modelEffortOptions} />
      </Field>
      <Field label="连接">
        <ModelConnectionTestAction registration={registration} />
      </Field>
    </div>
  );
}
