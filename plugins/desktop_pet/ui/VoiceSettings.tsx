import { compactGhostButtonClass, settingsGroupStackClass, usePrivateAutosave, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { VoicePreferences } from "../background/voice/preferences";
import { useVoiceEnvironment } from "./useVoiceEnvironment";
import { VoiceGroup, VoiceServicesGroup } from "./VoiceSettingsGroups";

/** The one private document this page edits. */
const preferencesIdentity = "voice.preferences";

/**
 * 设置 › 插件 › 桌宠. The voice preferences live in the plugin's private
 * backend storage, independently of host settings, and autosave like the
 * host's settings pages (runtime API 3.1.1).
 */
export function VoiceSettings({ client, host }: PluginSettingsSectionComponentProps) {
  const preferences = usePrivateAutosave<VoicePreferences>(client, preferencesIdentity, {
    load: () => client.call<VoicePreferences>("voice.preferences.get"),
    save: (value) => client.call<VoicePreferences>("voice.preferences.set", value),
  });
  const environment = useVoiceEnvironment(client);
  const { draft, loadError, saveError, savePhase, update, commit, retry, reload } = preferences;

  return (
    <div className={settingsGroupStackClass}>
      <host.ui.SettingsSavedStatus phase={savePhase} />
      {loadError ? (
        <host.ui.InlineError
          message={loadError}
          actions={<button type="button" className={compactGhostButtonClass} onClick={reload}>重新加载</button>}
        />
      ) : null}
      {/* A failed save pauses autosave; later edits wait for 重试 rather than look applied. */}
      {saveError ? (
        <host.ui.InlineError
          message={saveError}
          actions={<button type="button" className={compactGhostButtonClass} onClick={retry}>重试</button>}
        />
      ) : null}
      {draft ? (
        <>
          <VoiceGroup
            client={client}
            draft={draft}
            devices={environment.devices}
            devicesError={environment.devicesError}
            update={update}
            commit={commit}
          />
          <VoiceServicesGroup
            draft={draft}
            providers={environment.providers}
            providersError={environment.providersError}
            update={update}
          />
        </>
      ) : !loadError ? <span className="text-body-sm text-ink-muted">正在读取设置…</span> : null}
    </div>
  );
}
