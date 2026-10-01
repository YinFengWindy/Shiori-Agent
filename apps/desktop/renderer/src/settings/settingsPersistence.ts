import type {
  DesktopApi,
  SaveSettingsResult,
  SettingsFormData,
  SettingsSaveOptions,
  SettingsSnapshot,
} from "../../../src/bridge/shared.js";

type SettingsLoadApi = Pick<DesktopApi, "readSettings">;
type SettingsSaveApi = Pick<DesktopApi, "readSettings" | "saveSettings">;

/** Loaded editable configuration and its backend version. */
export type SettingsPageLoadResult = {
  snapshot: SettingsSnapshot;
};

/** Transaction outcome; a failed apply leaves the persisted snapshot untouched. */
export type SettingsPageSaveResult = {
  saveResult: SaveSettingsResult;
  snapshot: SettingsSnapshot | null;
  nextDraft: SettingsFormData;
  /** A confirmed write whose read-back failed; retry must only read. */
  refreshError?: unknown;
};

/** Deep-clones mutable settings form data before local edits. */
export function cloneSettings(data: SettingsFormData): SettingsFormData {
  return JSON.parse(JSON.stringify(data)) as SettingsFormData;
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

/** Loads the settings page data from the persisted runtime configuration. */
export async function loadSettingsPageData(api: SettingsLoadApi): Promise<SettingsPageLoadResult> {
  const nextSnapshot = await api.readSettings();
  return {
    snapshot: nextSnapshot,
  };
}

/** Atomically applies settings and deferred bindings, preserving failed drafts verbatim. */
export async function saveSettingsPageData(
  api: SettingsSaveApi,
  draft: SettingsFormData,
  options?: SettingsSaveOptions,
): Promise<SettingsPageSaveResult> {
  const saveResult = await api.saveSettings(cloneSettings(draft), options);
  return refreshSavedSettings(api, draft, saveResult);
}

/** Refreshes an acknowledged save without submitting the transaction a second time. */
export async function refreshSavedSettings(api: SettingsLoadApi, draft: SettingsFormData, saveResult: SaveSettingsResult): Promise<SettingsPageSaveResult> {
  let snapshot: SettingsSnapshot | null = null;
  if (saveResult.ok) {
    try { snapshot = await api.readSettings(); } catch (refreshError) {
      return { saveResult, snapshot: null, nextDraft: cloneSettings(draft), refreshError };
    }
  }
  const nextDraft = cloneSettings(snapshot?.formData ?? draft);

  return {
    saveResult,
    snapshot,
    nextDraft,
  };
}
