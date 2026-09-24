import { useCallback, useEffect, useRef } from "react";
import type React from "react";
import { readPluginRoleSettings, refreshPluginRoleDrafts } from "../plugins/pluginRoleSettings";
import { pluginRoleSettingsRegistry } from "../plugins/pluginFeatureRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { useLatestRef } from "../shared/useLatestRef";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { errorMessage } from "../shared/feedback/feedbackStore";

type RolePluginRefreshArgs = {
  detailRoleId: string;
  detailRole: RoleRecord | null;
  roleFormRef: React.MutableRefObject<RoleFormState>;
  loadRolesFromBridge: () => Promise<RoleRecord[] | null>;
  updateRoleForm: (next: React.SetStateAction<RoleFormState>) => void;
  reportError: (message: string) => void;
};

/** Reconciles plugin projections without replacing unrelated or newer draft edits. */
export function useRolePluginRefresh(args: RolePluginRefreshArgs) {
  const latest = useLatestRef(args);
  const request = useRef(0);
  const enabled = usePluginEnabledState();
  const lifecycleKey = pluginRoleSettingsRegistry.list().filter((entry) => entry.storage === "plugin")
    .map((entry) => `${entry.pluginId}:${enabled(entry.pluginId)}`).join("|");
  const refresh = useCallback((force = true) => refreshRolePlugins(latest, request, force), [latest]);

  useEffect(() => {
    // A cached role may lack projections while disabled. Stable lifecycle keys
    // prevent ordinary roster reloads from resetting an unsaved plugin draft.
    void refresh(false).catch((error: unknown) => latest.current.reportError(errorMessage(error)));
    return () => { request.current += 1; };
  }, [args.detailRoleId, lifecycleKey, latest, refresh]);

  return refresh;
}

async function refreshRolePlugins(latest: React.MutableRefObject<RolePluginRefreshArgs>, request: React.MutableRefObject<number>, force: boolean) {
  const { detailRoleId, detailRole, roleFormRef, loadRolesFromBridge } = latest.current;
  if (!detailRoleId) return;
  const generation = ++request.current;
  const initialDrafts = roleFormRef.current.pluginSettings;
  const expected = force ? initialDrafts : readPluginRoleSettings(detailRole?.runtime_config, detailRole?.plugin_state);
  const roles = await loadRolesFromBridge();
  if (generation !== request.current || latest.current.detailRoleId !== detailRoleId) return;
  const role = roles?.find((item) => item.id === detailRoleId);
  if (!role) return;
  latest.current.updateRoleForm((current) => {
    const pluginSettings = refreshPluginRoleDrafts(current.pluginSettings, role.plugin_state, expected);
    return pluginSettings === current.pluginSettings ? current : { ...current, pluginSettings };
  });
}
