import { useRef, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { ModelRegistrationFields } from "../settings/ModelRegistrationFields";
import { createModelRegistration } from "../settings/modelRegistration";
import { OnboardingCard } from "./OnboardingCard";
import { registerOnboardingModel } from "./onboardingData";
import type { OnboardingReaction } from "./onboardingScript";
import { onboardingActionClass } from "./onboardingStyles";

/** Submits one explicit model registration without auto-saving incomplete credentials. */
export function OnboardingModelStep({ onSaved, onBusyChange, onReact }: {
  onSaved: () => Promise<unknown>;
  onBusyChange: (busy: boolean) => void;
  onReact: (reaction: OnboardingReaction) => void;
}) {
  const [registration, setRegistration] = useState(createModelRegistration);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  async function save() {
    if (pending.current) return;
    pending.current = true;
    setSaving(true);
    onBusyChange(true);
    setError("");
    try {
      await registerOnboardingModel(window.miraDesktop, registration);
      await onSaved();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      onReact("modelSaveFailed");
    } finally {
      pending.current = false;
      setSaving(false);
      onBusyChange(false);
    }
  }
  return (
    <OnboardingCard title="注册模型" error={error} onSubmit={() => void save()} footer={(
      <button type="submit" className={onboardingActionClass} disabled={saving || !registration.model.trim() || !registration.provider.trim()}>
        {saving ? "正在保存" : "保存并继续"}<ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
    )}>
      <fieldset disabled={saving} className="m-0 min-w-0 border-0 p-0">
        <ModelRegistrationFields compact registration={registration} onChange={setRegistration}
          onConnectionTested={(outcome) => onReact(outcome.status === "success" ? "connectionOk" : "connectionFailed")} />
      </fieldset>
    </OnboardingCard>
  );
}
