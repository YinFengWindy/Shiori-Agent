import { ArrowLeft, Trash } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { SettingsField as Field } from "./SettingsField";
import { SettingsSecretInput, settingsInputClass } from "./SettingsFieldPrimitives";

type ModelRegistrationDetailsProps = {
  registration: ModelRegistrationFormData;
  canDelete: boolean;
  onBack: () => void;
  onChange: (
    mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData,
  ) => void;
  onDelete: () => void;
};

/** Renders the focused editor for one model registration. */
export function ModelRegistrationDetails({
  registration,
  canDelete,
  onBack,
  onChange,
  onDelete,
}: ModelRegistrationDetailsProps) {
  return (
    <section className="grid">
      <header className="flex min-h-11 items-center gap-3 border-b border-[#E7ECF1] pb-3">
        <button
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-[#667085] transition hover:bg-[#F3F6FA] hover:text-[#182230] focus:outline-none"
          type="button"
          aria-label="返回模型注册列表"
          title="返回模型注册列表"
          onClick={onBack}
        >
          <ArrowLeft className="h-4 w-4" weight="bold" />
        </button>
        <strong className="min-w-0 flex-1 truncate text-sm font-semibold text-[#182230]">
          {registration.model || "未配置模型"}
        </strong>
        <button
          className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-[#8A94A3] transition hover:bg-[#FFF1F1] hover:text-[#C83E3E] focus:outline-none disabled:cursor-not-allowed disabled:opacity-35"
          type="button"
          aria-label="删除模型注册"
          title="删除模型注册"
          disabled={!canDelete}
          onClick={onDelete}
        >
          <Trash className="h-4 w-4" weight="bold" />
        </button>
      </header>
      <div className="grid">
        <Field label="Provider">
          <input className={settingsInputClass} value={registration.provider} onChange={(event) => onChange((current) => ({ ...current, provider: event.target.value }))} />
        </Field>
        <Field label="模型">
          <input className={settingsInputClass} value={registration.model} onChange={(event) => onChange((current) => ({ ...current, model: event.target.value }))} />
        </Field>
        <Field label="Effort">
          <select className={settingsInputClass} value={registration.effort} onChange={(event) => onChange((current) => ({ ...current, effort: event.target.value as ModelRegistrationFormData["effort"] }))}>
            <option value="none">none</option>
            <option value="low">low</option>
            <option value="high">high</option>
            <option value="max">max</option>
          </select>
        </Field>
        <Field label="Base URL">
          <input className={settingsInputClass} value={registration.baseUrl} onChange={(event) => onChange((current) => ({ ...current, baseUrl: event.target.value }))} />
        </Field>
        <Field label="API Key">
          <SettingsSecretInput value={registration.apiKey} onChange={(value) => onChange((current) => ({ ...current, apiKey: value }))} />
        </Field>
      </div>
    </section>
  );
}
