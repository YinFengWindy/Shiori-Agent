import type {
  DesktopApi,
  SaveSettingsResult,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsSnapshot,
} from "../../../src/shared.js";
import type { RoleRecord } from "../shared/types.js";

type SettingsLoadApi = Pick<DesktopApi, "invoke" | "readChannelRoleBindings" | "readSettings">;
type SettingsSaveApi = Pick<
  DesktopApi,
  "readChannelRoleBindings" | "readSettings" | "saveChannelRoleBindings" | "saveSettings"
>;

export type SettingsPageLoadResult = {
  snapshot: SettingsSnapshot;
  roles: RoleRecord[];
};

export type SettingsPageSaveResult = {
  saveResult: SaveSettingsResult;
  snapshot: SettingsSnapshot;
  nextDraft: SettingsFormData;
  bindingsError: string;
};

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Deep-clones mutable settings form data before local edits. */
export function cloneSettings(data: SettingsFormData): SettingsFormData {
  return JSON.parse(JSON.stringify(data)) as SettingsFormData;
}

/** Replaces the form's channel-role bindings while preserving every other field. */
export function withSettingsRoleBindings(
  formData: SettingsFormData,
  roleBindings: SettingsChannelRoleBinding[],
): SettingsFormData {
  return {
    ...formData,
    channels: {
      ...formData.channels,
      roleBindings,
    },
  };
}

/** Hydrates the local settings snapshot with bridge-backed role-binding data. */
export function hydrateSettingsSnapshot(
  snapshot: SettingsSnapshot,
  roleBindings: SettingsChannelRoleBinding[],
): SettingsSnapshot {
  return {
    ...snapshot,
    formData: withSettingsRoleBindings(cloneSettings(snapshot.formData), roleBindings),
  };
}

/** Compares two settings payloads as persisted user data. */
export function settingsEqual(
  left: SettingsFormData | null,
  right: SettingsFormData | null,
): boolean {
  if (!left || !right) return false;
  return JSON.stringify(left) === JSON.stringify(right);
}

/** Returns whether a failed settings load should retry once the desktop bridge recovers. */
export function shouldRetryFailedSettingsLoad(options: {
  bridgeReady: boolean;
  loadError: string;
}): boolean {
  return options.bridgeReady && Boolean(options.loadError.trim());
}

/** Loads renderer settings data plus bridge-backed role lists and bindings. */
export async function loadSettingsPageData(api: SettingsLoadApi): Promise<SettingsPageLoadResult> {
  const [nextSnapshot, nextBindings, rolesResponse] = await Promise.all([
    api.readSettings(),
    api.readChannelRoleBindings(),
    api.invoke({
      method: "roles.list",
      payload: {},
    }),
  ]);
  if (rolesResponse.error) {
    throw new Error(rolesResponse.error.message);
  }
  return {
    snapshot: hydrateSettingsSnapshot(nextSnapshot, nextBindings.bindings),
    roles: Array.isArray(rolesResponse.payload.roles) ? rolesResponse.payload.roles as RoleRecord[] : [],
  };
}

/** Saves settings first, then role bindings, and preserves unsaved bindings after partial failures. */
export async function saveSettingsPageData(
  api: SettingsSaveApi,
  draft: SettingsFormData,
  currentSnapshot: SettingsSnapshot | null,
): Promise<SettingsPageSaveResult> {
  const saveResult = await api.saveSettings(draft);
  let bindingsError = "";
  let persistedBindings: SettingsChannelRoleBinding[] | null = null;

  if (saveResult.restart.ok) {
    try {
      const bindingsSnapshot = await api.saveChannelRoleBindings(draft.channels.roleBindings);
      persistedBindings = bindingsSnapshot.bindings;
    } catch (error) {
      bindingsError = getErrorMessage(error);
    }
  } else {
    bindingsError = "Bridge 重启失败，频道角色绑定未保存。";
  }

  const persistedSettings = await api.readSettings();
  if (!persistedBindings) {
    try {
      const bindingsSnapshot = await api.readChannelRoleBindings();
      persistedBindings = bindingsSnapshot.bindings;
    } catch (error) {
      persistedBindings = currentSnapshot?.formData.channels.roleBindings ?? [];
      if (!bindingsError) {
        bindingsError = getErrorMessage(error);
      }
    }
  }

  const snapshot = hydrateSettingsSnapshot(persistedSettings, persistedBindings);
  const nextDraft = bindingsError
    ? withSettingsRoleBindings(cloneSettings(snapshot.formData), draft.channels.roleBindings)
    : cloneSettings(snapshot.formData);

  return {
    saveResult,
    snapshot,
    nextDraft,
    bindingsError,
  };
}
