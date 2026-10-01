import { BridgeError, errorMessage } from "@shiori/plugin-sdk";
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
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  async function save() {
    if (pending.current) return;
    pending.current = true;
    setSaving(true);
    onBusyChange(true);
    setError("");
    let confirmed = saved;
    try {
      if (confirmed) await window.miraDesktop.readSettings();
      else {
        await registerOnboardingModel(window.miraDesktop, registration);
        confirmed = true;
        setSaved(true);
      }
      await onSaved();
    } catch (error) {
      // This owning error code is emitted only after saveSettings acknowledged
      // success. Recovery reads the saved state instead of issuing a new write.
      confirmed ||= error instanceof BridgeError && error.code === "settings_refresh_failed";
      if (confirmed) setSaved(true);
      const cause = errorMessage(error, { includeDetail: true });
      setError(confirmed ? `模型已保存，后续步骤未完成。请重新加载后继续。\n${cause}` : cause);
      onReact("modelSaveFailed");
    } finally {
      pending.current = false;
      setSaving(false);
      onBusyChange(false);
    }
  }
  return (
    <OnboardingCard title="注册模型" error={error} onSubmit={() => void save()} footer={(
      <button type="submit" className={onboardingActionClass} disabled={saving || (!saved && (!registration.model.trim() || !registration.provider.trim()))}>
        {saved ? saving ? "正在重新加载" : "重新加载并继续" : saving ? "正在保存" : "保存并继续"}<ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
    )}>
      <fieldset disabled={saving || saved} className="m-0 min-w-0 border-0 p-0">
        <ModelRegistrationFields compact registration={registration} onChange={setRegistration}
          onConnectionTested={(outcome) => onReact(outcome.status === "success" ? "connectionOk" : "connectionFailed")} />
      </fieldset>
    </OnboardingCard>
  );
}
