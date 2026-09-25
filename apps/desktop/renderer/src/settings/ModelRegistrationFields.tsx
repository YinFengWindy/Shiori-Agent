import { useState } from "react";
import { Select } from "../shared/ui/Select";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortOptions } from "../shared/modelEffortLabels";
import { SettingsField } from "./SettingsField";
import type { ModelConnectionTestOutcome } from "./modelConnectionTest";
import { SettingsSecretInput, settingsInputClass } from "./SettingsFieldPrimitives";
import { ModelConnectionTestAction } from "./ModelConnectionTestAction";
import { applyProviderPreset, customProviderPresetId, findProviderPreset, modelProviderOptions } from "./modelProviderPresets";

/**
 * Model registration fields shared by the catalog and first-run setup.
 * `compact` stacks every label over its control with tighter rows, for the
 * guide's floating card; `onConnectionTested` observes each finished probe.
 */
export function ModelRegistrationFields({ registration, onChange, compact = false, onConnectionTested }: {
  registration: ModelRegistrationFormData;
  onChange: (mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData) => void;
  compact?: boolean;
  onConnectionTested?: (result: ModelConnectionTestOutcome) => void;
}) {
  const fieldLayout = { layout: compact ? "stack" : "side", dense: compact } as const;
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
      <SettingsField {...fieldLayout} label="服务商">
        <Select aria-label="服务商" className={inputClass} value={preset?.id ?? customProviderPresetId} onValueChange={choosePreset} options={modelProviderOptions} />
      </SettingsField>
      {preset ? null : (
        <SettingsField {...fieldLayout} label="服务商标识">
          <input aria-label="服务商标识" className={inputClass} placeholder="openai" value={registration.provider} onChange={(event) => onChange((current) => ({ ...current, provider: event.target.value }))} />
        </SettingsField>
      )}
      {/* 「Base URL」 stays as the muted secondary line: it is what provider docs call the field. */}
      <SettingsField {...fieldLayout} label="服务地址" hint="Base URL">
        <input aria-label="服务地址" className={inputClass} placeholder="https://example.com/v1" value={registration.baseUrl} onChange={(event) => onChange((current) => ({ ...current, baseUrl: event.target.value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="API Key">
        <SettingsSecretInput ariaLabel="API Key" value={registration.apiKey} onChange={(value) => onChange((current) => ({ ...current, apiKey: value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="模型">
        <input aria-label="模型" className={inputClass} placeholder={preset?.modelHint} value={registration.model} onChange={(event) => onChange((current) => ({ ...current, model: event.target.value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="思考强度">
        <Select aria-label="思考强度" className={inputClass} value={registration.effort} onValueChange={(value) => onChange((current) => ({ ...current, effort: value as ModelRegistrationFormData["effort"] }))} options={modelEffortOptions} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="连接">
        <ModelConnectionTestAction registration={registration} onTested={onConnectionTested} />
      </SettingsField>
    </div>
  );
}
