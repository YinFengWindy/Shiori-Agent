import { useState } from "react";
import { Select } from "@yinfengwindy/shiori-sdk";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortOptions } from "../shared/modelEffortLabels";
import { SettingsField } from "./SettingsField";
import type { ModelConnectionTestOutcome } from "./modelConnectionTest";
import { SettingsSecretInput, settingsInputClass } from "./SettingsFieldPrimitives";
import { ModelConnectionTestAction } from "./ModelConnectionTestAction";
import { modelCapacityErrors } from "../../../src/settingsContract.js";
import { InlineError } from "../shared/feedback/InlineError";
import { applyProviderPreset, customProviderPresetId, findProviderPreset, modelProviderOptions } from "./modelProviderPresets";

function optionalTokenCount(value: string) {
  return value === "" ? null : Number(value);
}

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
  const capacityErrors = modelCapacityErrors(registration);
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
      <SettingsField {...fieldLayout} label="Base URL">
        <input aria-label="Base URL" className={inputClass} placeholder="https://example.com/v1" value={registration.baseUrl} onChange={(event) => onChange((current) => ({ ...current, baseUrl: event.target.value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="API Key">
        <SettingsSecretInput ariaLabel="API Key" value={registration.apiKey} onChange={(value) => onChange((current) => ({ ...current, apiKey: value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="模型">
        <input aria-label="模型" className={inputClass} placeholder={preset?.modelHint} value={registration.model} onChange={(event) => onChange((current) => ({ ...current, model: event.target.value }))} />
      </SettingsField>
      <SettingsField {...fieldLayout} label="上下文窗口（token）">
        <div className="grid gap-2">
          <input aria-label="上下文窗口" className={inputClass} type="number" min="1" step="1" required placeholder="需补填" value={registration.modelContextWindow ?? ""} onChange={(event) => onChange((current) => ({ ...current, modelContextWindow: optionalTokenCount(event.target.value) }))} />
          {capacityErrors.modelContextWindow ? <InlineError persona={false} message={capacityErrors.modelContextWindow} /> : null}
        </div>
      </SettingsField>
      <SettingsField {...fieldLayout} label="自动压缩阈值（token）">
        <div className="grid gap-2">
          <input aria-label="自动压缩阈值" className={inputClass} type="number" min="1" step="1" placeholder="可选" value={registration.modelAutoCompactTokenLimit ?? ""} onChange={(event) => onChange((current) => ({ ...current, modelAutoCompactTokenLimit: optionalTokenCount(event.target.value) }))} />
          {capacityErrors.modelAutoCompactTokenLimit ? <InlineError persona={false} message={capacityErrors.modelAutoCompactTokenLimit} /> : null}
        </div>
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
