import { useEffect, useRef } from "react";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import type { PluginHostFeedback } from "../../../apps/desktop/renderer/src/plugins/pluginHostFeedback";
import { failurePersona, type GenerationFailure } from "./generationFailure";
import { loadHistory, refreshReadiness, submitGenerate } from "./novelAiGeneration";
import { clearFailure, getNovelAiState, updateStudioForm, useNovelAiPageStore } from "./novelAiPageStore";
import { buildGeneratePayload, canSubmitStudioForm, resolveStudioRoleId, validateStudioForm } from "./studioForm";
import { selectGenerationBlocked, selectStageView } from "./studioSelectors";
import { useNovelAiPromptSettings } from "./useNovelAiPromptSettings";

/**
 * Raises the toast for a failed generation through the host queue, fronted by
 * 吟风 with the scene of its failure kind (`failurePersona`); token problems
 * carry a jump to the plugin's settings. While the failure card is on screen
 * it already says her line, so the toast shows only her face then.
 */
export function reportGenerationFailure(report: PluginHostFeedback, failure: GenerationFailure, { onOpenSettings, cardOnScreen = false }: {
  onOpenSettings?: () => void;
  /** The stage shows this failure's card (with her line) right now. */
  cardOnScreen?: boolean;
} = {}): void {
  report.error(failure.title, {
    persona: failurePersona(failure),
    personaQuiet: cardOnScreen,
    detail: failure.message || undefined,
    action: failure.opensSettings && onOpenSettings ? { label: "去设置", onSelect: onOpenSettings } : undefined,
  });
}

/**
 * Everything the studio view needs: the shared form and canvas state, the
 * config-backed prompt switches, and the generate/pick actions. Keeps the
 * generation role valid as the roster or the role open in chat changes, and
 * loads that role's history.
 */
export function useImageStudio(client: PluginRpcClient, activeRoleId: string, onOpenSettings?: () => void) {
  const host = usePluginHostServices();
  const store = useNovelAiPageStore();
  const settings = useNovelAiPromptSettings();
  const { form, roles, rolesLoaded } = store;
  // Read after the generate call resolves: the user may have left the studio meanwhile.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    void refreshReadiness(client);
  }, [client]);

  useEffect(() => {
    if (!rolesLoaded) return;
    updateStudioForm({ roleId: resolveStudioRoleId(form.roleId, activeRoleId, roles.map((role) => role.id)) });
  }, [activeRoleId, form.roleId, roles, rolesLoaded]);

  useEffect(() => {
    if (!rolesLoaded) return;
    void loadHistory(client, host.feedback, form.roleId);
  }, [client, form.roleId, host.feedback, rolesLoaded]);

  const blocked = selectGenerationBlocked(store.readiness);

  async function submit(): Promise<void> {
    // An emptied prompt means the failed attempt was abandoned; its message goes with it.
    if (!form.prompt.trim()) {
      clearFailure();
      return;
    }
    if (!canSubmitStudioForm(form) || blocked || store.submitting) return;
    const failure = await submitGenerate(client, host.feedback, buildGeneratePayload(form, settings.model));
    // The card is on screen only if the studio is still mounted and the stage shows the failure.
    const cardOnScreen = mounted.current && selectStageView(getNovelAiState()).kind === "failure";
    if (failure) reportGenerationFailure(host.feedback, failure, { onOpenSettings, cardOnScreen });
  }

  async function pickBaseImage(): Promise<void> {
    const [path] = await host.pickImages({ multiple: false });
    if (path) updateStudioForm({ baseImagePath: path });
  }

  return {
    store,
    settings,
    stage: selectStageView(store),
    blocked,
    validationError: validateStudioForm(form),
    canSubmit: rolesLoaded && !blocked && !store.submitting && canSubmitStudioForm(form),
    submit,
    pickBaseImage,
  };
}
