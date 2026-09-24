import { useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { createModelRegistration, isModelRegistrationComplete } from "./modelRegistration";

type Mutation = (registration: ModelRegistrationFormData) => ModelRegistrationFormData;

/**
 * Holds a 「添加模型」 entry outside the autosaved settings draft until it is
 * complete (`isModelRegistrationComplete`), so an abandoned or half-filled
 * form never persists an empty 「未配置模型」 registration. The edit that
 * completes it hands it to `onCommit` and ends the draft; leaving the page
 * discards it.
 */
export function useModelRegistrationDraft(onCommit: (registration: ModelRegistrationFormData) => void) {
  const [draft, setDraft] = useState<ModelRegistrationFormData | null>(null);

  function update(mutate: Mutation): void {
    if (!draft) return;
    const next = mutate(draft);
    if (isModelRegistrationComplete(next)) {
      setDraft(null);
      onCommit(next);
      return;
    }
    setDraft(next);
  }

  return {
    draft,
    start: () => setDraft(createModelRegistration()),
    update,
    discard: () => setDraft(null),
  };
}
