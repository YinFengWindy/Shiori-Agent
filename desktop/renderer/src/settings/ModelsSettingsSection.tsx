import { Plus, Trash } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/shared";
import type { RoleRecord } from "../shared/types";
import { SettingsField as Field } from "./SettingsField";
import {
  SettingsSecretInput,
  SettingsSectionCard,
  settingsInputClass,
} from "./SettingsFieldPrimitives";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";

function createRegistration(): ModelRegistrationFormData {
  return {
    id: crypto.randomUUID(),
    provider: "openai",
    baseUrl: "",
    apiKey: "",
    model: "",
    effort: "none",
  };
}

/** Renders the editable global model registration catalog. */
export function ModelsSettingsSection({
  draft,
  updateDraft,
}: SettingsSectionEditorProps) {
  function updateRegistration(
    id: string,
    mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData,
  ): void {
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: current.models.registrations.map((registration) => (
          registration.id === id ? mutate(registration) : registration
        )),
      },
    }));
  }

  async function removeRegistration(registration: ModelRegistrationFormData): Promise<void> {
    if (draft.models.registrations.length <= 1) return;
    const response = await window.miraDesktop.invoke({ method: "roles.list", payload: {} });
    if (response.error) {
      window.alert(response.error.message);
      return;
    }
    const roles = Array.isArray(response.payload.roles) ? response.payload.roles as RoleRecord[] : [];
    const affectedRoles = roles.filter((role) => (
      role.runtime_config.dialogue_model_registration_id === registration.id
      || role.runtime_config.visual_model_registration_id === registration.id
    ));
    const impact = affectedRoles.length > 0
      ? `\n受影响角色：${affectedRoles.map((role) => role.name).join("、")}`
      : "";
    if (!window.confirm(`删除模型注册“${registration.model}”？${impact}`)) return;
    const remaining = draft.models.registrations.filter((item) => item.id !== registration.id);
    const fallbackId = remaining[0]?.id ?? "";
    try {
      await Promise.all(affectedRoles.map(async (role) => {
        const runtimeConfig = {
          ...role.runtime_config,
          dialogue_model_registration_id: role.runtime_config.dialogue_model_registration_id === registration.id
            ? fallbackId
            : role.runtime_config.dialogue_model_registration_id,
          visual_model_registration_id: role.runtime_config.visual_model_registration_id === registration.id
            ? ""
            : role.runtime_config.visual_model_registration_id,
        };
        const updateResponse = await window.miraDesktop.invoke({
          method: "roles.update",
          payload: { role_id: role.id, runtime_config: runtimeConfig },
        });
        if (updateResponse.error) throw new Error(updateResponse.error.message);
      }));
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error));
      return;
    }
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: current.models.registrations.filter((item) => item.id !== registration.id),
      },
    }));
  }

  return (
    <SettingsSectionCard>
      <div className="grid gap-5">
        {draft.models.registrations.map((registration) => (
          <section className="grid gap-4 border-b border-[#E8EDF2] pb-5 last:border-b-0 last:pb-0" key={registration.id}>
            <div className="flex items-center justify-between gap-3">
              <strong className="truncate text-sm font-semibold text-[#182230]">
                {registration.model || "未配置模型"}
              </strong>
              <button
                className="grid h-8 w-8 place-items-center rounded-md text-[#8A94A3] transition hover:bg-[#FFF1F1] hover:text-[#C83E3E] focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-35"
                type="button"
                title="删除模型注册"
                aria-label="删除模型注册"
                disabled={draft.models.registrations.length <= 1}
                onClick={() => void removeRegistration(registration)}
              >
                <Trash className="h-4 w-4" weight="bold" />
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Provider">
                <input className={settingsInputClass} value={registration.provider} onChange={(event) => updateRegistration(registration.id, (current) => ({ ...current, provider: event.target.value }))} />
              </Field>
              <Field label="模型">
                <input className={settingsInputClass} value={registration.model} onChange={(event) => updateRegistration(registration.id, (current) => ({ ...current, model: event.target.value }))} />
              </Field>
              <Field label="Effort">
                <select className={settingsInputClass} value={registration.effort} onChange={(event) => updateRegistration(registration.id, (current) => ({ ...current, effort: event.target.value as ModelRegistrationFormData["effort"] }))}>
                  <option value="none">none</option>
                  <option value="low">low</option>
                  <option value="high">high</option>
                  <option value="max">max</option>
                </select>
              </Field>
              <Field label="Base URL">
                <input className={settingsInputClass} value={registration.baseUrl} onChange={(event) => updateRegistration(registration.id, (current) => ({ ...current, baseUrl: event.target.value }))} />
              </Field>
              <Field label="API Key">
                <SettingsSecretInput value={registration.apiKey} onChange={(value) => updateRegistration(registration.id, (current) => ({ ...current, apiKey: value }))} />
              </Field>
            </div>
          </section>
        ))}
        <button
          className="inline-flex h-9 w-fit items-center gap-2 rounded-md border border-[#D8DFE7] bg-white px-3 text-sm font-medium text-[#344054] transition hover:bg-[#F7F9FB] focus:outline-none focus:ring-2 focus:ring-primary/20"
          type="button"
          onClick={() => updateDraft((current) => ({ ...current, models: { registrations: [...current.models.registrations, createRegistration()] } }))}
        >
          <Plus className="h-4 w-4" weight="bold" />
          新建注册
        </button>
      </div>
    </SettingsSectionCard>
  );
}
