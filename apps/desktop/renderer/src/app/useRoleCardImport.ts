import { useEffect, useRef, useState } from "react";
import type { NewRoleFormState } from "../shared/types";
import { useLatestRef } from "../shared/useLatestRef";
import { createRoleFormFromImport, idleRoleCardImport, readRoleCardImportPreview } from "./roleCardImportState";
import type { RoleCardImportState } from "./roleCardImportState";
import { errorMessage, type FeedbackOptions } from "../shared/feedback/feedbackStore";
import { describeRoleCardImportError } from "../roles/roleCardImportErrors";

type ImportControllerArgs = {
  updateNewRoleForm: (next: React.SetStateAction<NewRoleFormState>) => void;
  /**
   * Receives the already-prefixed, user-facing failure message, plus the raw
   * cause as `detail` when the message rewrote it; the caller decides where it is shown.
   */
  reportImportError: (message: string, options?: FeedbackOptions) => void;
};

async function releasePreview(importId: string) {
  const response = await window.miraDesktop.invoke({ method: "roles.cardImport.cancel", payload: { import_id: importId } });
  if (response.error) throw new Error(response.error.message);
}

/** Owns staging and invalidates stale preview responses when a draft is cancelled or reset. */
export function useRoleCardImport({ updateNewRoleForm, reportImportError }: ImportControllerArgs) {
  const [roleCardImport, setRoleCardImport] = useState(idleRoleCardImport);
  const currentImportRef = useLatestRef(roleCardImport);
  const generation = useRef(0);
  useEffect(() => () => { generation.current += 1; }, []);

  function updateImport(next: RoleCardImportState) {
    currentImportRef.current = next;
    setRoleCardImport(next);
  }

  function clearRoleCardImport() {
    generation.current += 1;
    updateImport(idleRoleCardImport);
  }

  function reportError(error: unknown) {
    const { message, detail } = describeRoleCardImportError(errorMessage(error));
    // 吟风 has her own line for an unreadable card (the host reporter shows it when she is on).
    reportImportError(message, { persona: "roleImportFailed", ...(detail ? { detail } : {}) });
  }

  async function previewRoleCard() {
    if (currentImportRef.current.status !== "idle") return;
    const requestGeneration = ++generation.current;
    updateImport({ status: "previewing", preview: null, source: "" });
    try {
      const source = await window.miraDesktop.pickRoleCard();
      if (requestGeneration !== generation.current) return;
      if (!source) { updateImport(idleRoleCardImport); return; }
      updateImport({ status: "previewing", preview: null, source });
      const response = await window.miraDesktop.invoke({ method: "roles.cardImport.preview", payload: { source } });
      if (response.error) throw new Error(response.error.message);
      const preview = readRoleCardImportPreview(response.payload);
      if (requestGeneration !== generation.current) {
        await releasePreview(preview.import_id);
        return;
      }
      updateImport({ status: "ready", preview, source });
      updateNewRoleForm(createRoleFormFromImport(preview));
    } catch (error) {
      if (requestGeneration === generation.current) {
        updateImport(idleRoleCardImport);
        reportError(error);
      }
    }
  }

  async function cancelRoleCardImport() {
    const importId = currentImportRef.current.preview?.import_id;
    clearRoleCardImport();
    updateNewRoleForm((current) => ({ ...current, importId: undefined, emotionSelections: undefined }));
    if (!importId) return;
    try { await releasePreview(importId); } catch (error) { reportError(error); }
  }

  return { roleCardImport, clearRoleCardImport, previewRoleCard, cancelRoleCardImport };
}
