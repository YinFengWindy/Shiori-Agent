import { useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/shared";
import { ModelRegistrationDetails } from "./ModelRegistrationDetails";
import { ModelRegistrationList } from "./ModelRegistrationList";
import { prepareModelRegistrationRemoval } from "./modelRegistrationRemoval";
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

/** Renders the model registration catalog as list and detail views. */
export function ModelsSettingsSection({
  draft,
  updateDraft,
}: SettingsSectionEditorProps) {
  const [activeRegistrationId, setActiveRegistrationId] = useState<string | null>(null);
  const activeRegistration = draft.models.registrations.find(
    (registration) => registration.id === activeRegistrationId,
  ) ?? null;

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

  function addRegistration(): void {
    const registration = createRegistration();
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: [...current.models.registrations, registration],
      },
    }));
    setActiveRegistrationId(registration.id);
  }

  async function removeRegistration(registration: ModelRegistrationFormData): Promise<void> {
    const canRemove = await prepareModelRegistrationRemoval(
      registration,
      draft.models.registrations,
    );
    if (!canRemove) return;
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: current.models.registrations.filter((item) => item.id !== registration.id),
      },
      pendingRoleModelUpdates: [
        ...(current.pendingRoleModelUpdates ?? []).filter(
          (item) => !canRemove.some((update) => update.roleId === item.roleId),
        ),
        ...canRemove,
      ],
    }));
    setActiveRegistrationId(null);
  }

  if (activeRegistration) {
    return (
      <ModelRegistrationDetails
        registration={activeRegistration}
        canDelete={draft.models.registrations.length > 1}
        onBack={() => setActiveRegistrationId(null)}
        onChange={(mutate) => updateRegistration(activeRegistration.id, mutate)}
        onDelete={() => void removeRegistration(activeRegistration)}
      />
    );
  }

  return (
    <ModelRegistrationList
      registrations={draft.models.registrations}
      onCreate={addRegistration}
      onOpen={setActiveRegistrationId}
    />
  );
}
