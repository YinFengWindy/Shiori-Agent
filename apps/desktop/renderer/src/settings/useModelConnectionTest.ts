import { useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelConnectionKey, selectModelConnectionTestView, testModelConnection, type ModelConnectionTestRecord } from "./modelConnectionTest";

/** Runs `models.test` for the current draft and exposes the result for these exact fields. */
export function useModelConnectionTest(registration: ModelRegistrationFormData) {
  const [record, setRecord] = useState<ModelConnectionTestRecord | null>(null);
  const view = selectModelConnectionTestView(record, registration);
  const run = async () => {
    const key = modelConnectionKey(registration);
    setRecord({ key, view: { status: "testing" } });
    let next: ModelConnectionTestRecord;
    try {
      next = { key, view: await testModelConnection(window.miraDesktop.invoke, registration) };
    } catch (error) {
      next = { key, view: { status: "failure", message: error instanceof Error ? error.message : String(error) } };
    }
    // A slower probe of an earlier draft must not overwrite a newer one.
    setRecord((current) => (current?.key === key ? next : current));
  };
  return { view, run };
}
