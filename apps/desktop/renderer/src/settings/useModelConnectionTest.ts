import { useState } from "react";
import { useLatestRef } from "../shared/useLatestRef";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelConnectionKey, selectModelConnectionTestView, testModelConnection, type ModelConnectionTestOutcome, type ModelConnectionTestRecord } from "./modelConnectionTest";

/**
 * Runs `models.test` for the current draft and exposes the result for these
 * exact fields; `onTested` hears every finished probe that is still current.
 */
export function useModelConnectionTest(registration: ModelRegistrationFormData, onTested?: (outcome: ModelConnectionTestOutcome) => void) {
  const [record, setRecord] = useState<ModelConnectionTestRecord | null>(null);
  // Which draft is on screen when a probe returns; stale probes stay silent.
  const latestKey = useLatestRef(modelConnectionKey(registration));
  const view = selectModelConnectionTestView(record, registration);
  const run = async () => {
    const key = modelConnectionKey(registration);
    setRecord({ key, view: { status: "testing" } });
    let outcome: ModelConnectionTestOutcome;
    try {
      outcome = await testModelConnection(window.miraDesktop.invoke, registration);
    } catch (error) {
      outcome = { status: "failure", message: error instanceof Error ? error.message : String(error) };
    }
    // A slower probe of an earlier draft must not overwrite a newer one.
    setRecord((current) => (current?.key === key ? { key, view: outcome } : current));
    if (latestKey.current === key) onTested?.(outcome);
  };
  return { view, run };
}
