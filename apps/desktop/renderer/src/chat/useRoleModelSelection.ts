import { useCallback, useEffect, useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import type { RoleRecord } from "../shared/types";
import { errorMessage, feedback } from "../shared/feedback/feedbackStore";
import {
  runtimeConfigForSelection,
  selectionFromRole,
  type ModelEffort,
  type RoleModelSelection,
} from "./chatModelSelection";

/** One change the chat model menu can make to the role's model binding. */
export type RoleModelSelectionChange = "dialogue" | "visual" | "dialogueEffort" | "visualEffort";

/**
 * Loads the model registrations and the active role's model/effort binding,
 * and writes changes back through `roles.update`. Failures surface as error
 * toasts; the menu keeps the last good selection.
 */
export function useRoleModelSelection(activeRoleId: string, bridgeReady: boolean) {
  const [registrations, setRegistrations] = useState<ModelRegistrationFormData[]>([]);
  const [selection, setSelection] = useState<RoleModelSelection | null>(null);

  const reload = useCallback(async () => {
    if (!activeRoleId || !bridgeReady) return;
    try {
      const [settings, rolesResponse] = await Promise.all([
        window.miraDesktop.readSettings(),
        window.miraDesktop.invoke({ method: "roles.list", payload: {} }),
      ]);
      if (rolesResponse.error) throw new Error(rolesResponse.error.message);
      const roles = Array.isArray(rolesResponse.payload.roles)
        ? rolesResponse.payload.roles as RoleRecord[]
        : [];
      const role = roles.find((item) => item.id === activeRoleId);
      if (!role) throw new Error("当前角色不存在");
      setRegistrations(settings.formData.models.registrations);
      setSelection(selectionFromRole(role, settings.formData.models.registrations));
    } catch (error) {
      feedback.error(`模型选项加载失败：${errorMessage(error)}`);
    }
  }, [activeRoleId, bridgeReady]);

  useEffect(() => {
    setSelection(null);
    void reload();
  }, [reload]);

  const update = useCallback(async (kind: RoleModelSelectionChange, value: string) => {
    if (!selection || !activeRoleId) return;
    const runtimeConfig = runtimeConfigForSelection(selection, kind, value);
    try {
      const response = await window.miraDesktop.invoke({
        method: "roles.update",
        payload: { role_id: activeRoleId, runtime_config: runtimeConfig },
      });
      if (response.error) throw new Error(response.error.message);
      const role = response.payload.role as RoleRecord | undefined;
      setSelection(role ? selectionFromRole(role, registrations) : {
        dialogueId: String(runtimeConfig.dialogue_model_registration_id),
        visualId: String(runtimeConfig.visual_model_registration_id),
        dialogueEffort: String(runtimeConfig.dialogue_model_effort) as ModelEffort,
        visualEffort: String(runtimeConfig.visual_model_effort) as ModelEffort,
        runtimeConfig,
      });
    } catch (error) {
      feedback.error(`模型切换失败：${errorMessage(error)}`);
    }
  }, [activeRoleId, registrations, selection]);

  return { registrations, selection, reload, update };
}
