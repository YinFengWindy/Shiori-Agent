import { useEffect } from "react";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { feedback } from "../../../apps/desktop/renderer/src/shared/feedback/feedbackStore";
import type { GenerationFailure } from "./generationFailure";
import { loadHistory, refreshReadiness, submitGenerate } from "./novelAiGeneration";
import { clearFailure, updateStudioForm, useNovelAiPageStore } from "./novelAiPageStore";
import { buildGeneratePayload, canSubmitStudioForm, resolveStudioRoleId, validateStudioForm } from "./studioForm";
import { selectGenerationBlocked, selectStageView } from "./studioSelectors";
import { useNovelAiPromptSettings } from "./useNovelAiPromptSettings";

/** Raises the toast for a failed generation; token problems carry a jump to the plugin's settings. */
export function reportGenerationFailure(failure: GenerationFailure, onOpenSettings?: () => void): void {
  feedback.error(failure.title, {
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

  useEffect(() => {
    void refreshReadiness(client);
  }, [client]);

  useEffect(() => {
    if (!rolesLoaded) return;
    updateStudioForm({ roleId: resolveStudioRoleId(form.roleId, activeRoleId, roles.map((role) => role.id)) });
  }, [activeRoleId, form.roleId, roles, rolesLoaded]);

  useEffect(() => {
    if (!rolesLoaded) return;
    void loadHistory(client, form.roleId);
  }, [client, form.roleId, rolesLoaded]);

  const blocked = selectGenerationBlocked(store.readiness);

  async function submit(): Promise<void> {
    // An emptied prompt means the failed attempt was abandoned; its message goes with it.
    if (!form.prompt.trim()) {
      clearFailure();
      return;
    }
    if (!canSubmitStudioForm(form) || blocked || store.submitting) return;
    const failure = await submitGenerate(client, buildGeneratePayload(form, settings.model));
    if (failure) reportGenerationFailure(failure, onOpenSettings);
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
