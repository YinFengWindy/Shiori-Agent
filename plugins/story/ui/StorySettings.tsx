import { ArrowLeft } from "@phosphor-icons/react";
import { useEffect, useState, type ReactNode } from "react";
import type { PluginServiceDescriptor } from "@yinfengwindy/shiori-sdk";
import { StoryError } from "./StoryError";
import { describeStoryFailure } from "./storyFailure";
import type { StoryVoiceSource } from "./storyVoice";
import { StorySegmentedControl, StoryToggle, StoryVolumeControl } from "./StorySettingsControls";
import { StorySurface } from "./StorySurface";
import { updateStoryPreferences, useStoryPreferences, type StoryPace } from "./storyPreferences";
import { storyIconButtonClass, storyInputClass, storyPageHeaderClass, storyPageTitleClass, storyGutterClass, storySectionTitleClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StorySettingsProps = { background?: StoryMenuBackground; sharedBackdrop?: boolean; voiceSource?: StoryVoiceSource; onBack: () => void };

type ProviderList = { providers: PluginServiceDescriptor[] | null; failure: ReturnType<typeof describeStoryFailure> | null };

const paceOptions = [
  { value: "slow", label: "慢" },
  { value: "normal", label: "标准" },
  { value: "fast", label: "快" },
] as const satisfies readonly { value: StoryPace; label: string }[];

const rowClass = "flex min-h-14 items-center justify-between gap-6 border-b border-[color:var(--story-line-soft)] py-3 text-sm last:border-b-0";
const rowLabelClass = "font-medium text-[color:var(--story-ink-strong)]";

function SettingRow({ label, children }: { label: string; children: ReactNode }) {
  return <div className={rowClass}><span className={rowLabelClass}>{label}</span><div className="w-[min(16rem,55%)] shrink-0 [&>[role=switch]]:ml-auto [&>[role=switch]]:flex">{children}</div></div>;
}

function providerValue(provider: { plugin_id: string; service_id: string } | null) {
  return provider ? `${provider.plugin_id}/${provider.service_id}` : "";
}

/** Lists installed TTS providers once per source; a failed listing keeps the saved choice visible. */
function useTtsProviders(voiceSource: StoryVoiceSource | undefined): ProviderList {
  const [state, setState] = useState<ProviderList & { source: StoryVoiceSource | undefined }>({ source: undefined, providers: null, failure: null });
  useEffect(() => {
    if (!voiceSource) return;
    let active = true;
    voiceSource.listProviders().then(
      (providers) => { if (active) setState({ source: voiceSource, providers, failure: null }); },
      (cause: unknown) => { if (active) setState({ source: voiceSource, providers: null, failure: describeStoryFailure(cause, "语音服务列表读取失败") }); },
    );
    return () => { active = false; };
  }, [voiceSource]);
  return state.source === voiceSource ? state : { providers: null, failure: null };
}

/** Renders the Story playback preferences; every change applies immediately to the running Story. */
export function StorySettings({ background, sharedBackdrop = false, voiceSource, onBack }: StorySettingsProps) {
  const settings = useStoryPreferences();
  const { providers, failure } = useTtsProviders(voiceSource);
  const selected = providerValue(settings.voiceProvider);
  const selectedMissing = Boolean(settings.voiceProvider) && providers !== null && !providers.some((provider) => providerValue(provider) === selected);

  return (
    <StorySurface background={background} sharedBackdrop={sharedBackdrop} dataTestId="story-settings" panelTestId="story-settings-panel">
      <header className={storyPageHeaderClass}>
        <button className={storyIconButtonClass} type="button" aria-label="返回" title="返回" onClick={onBack}>
          <ArrowLeft className="h-5 w-5" weight="bold" />
        </button>
        <h1 className={storyPageTitleClass}>设置</h1>
      </header>

      <div className={`${storyGutterClass} py-7`}>
        <div className="mx-auto grid w-full max-w-2xl">
          <SettingRow label="文字速度"><StorySegmentedControl value={settings.textSpeed} options={paceOptions} ariaLabel="文字速度" disabled={settings.showFullText} onChange={(value) => updateStoryPreferences({ textSpeed: value })} /></SettingRow>
          <SettingRow label="立即显示全文"><StoryToggle checked={settings.showFullText} label="立即显示全文" onChange={(value) => updateStoryPreferences({ showFullText: value })} /></SettingRow>
          <SettingRow label="自动播放"><StoryToggle checked={settings.autoPlay} label="自动播放" onChange={(value) => updateStoryPreferences({ autoPlay: value })} /></SettingRow>
          <SettingRow label="自动播放速度"><StorySegmentedControl value={settings.autoPlaySpeed} options={paceOptions} ariaLabel="自动播放速度" disabled={!settings.autoPlay} onChange={(value) => updateStoryPreferences({ autoPlaySpeed: value })} /></SettingRow>
          <SettingRow label="减少动态效果"><StoryToggle checked={settings.reducedMotion} label="减少动态效果" onChange={(value) => updateStoryPreferences({ reducedMotion: value })} /></SettingRow>

          <h2 className={`${storySectionTitleClass} mt-8 border-b border-[color:var(--story-line)] pb-3`}>角色语音</h2>
          <SettingRow label="语音服务">
            <select className={storyInputClass} aria-label="语音服务" value={selected} disabled={!voiceSource} onChange={(event) => {
              const next = providers?.find((provider) => providerValue(provider) === event.target.value);
              updateStoryPreferences({ voiceProvider: next ? { plugin_id: next.plugin_id, service_id: next.service_id } : null });
            }}>
              <option value="">不朗读</option>
              {selectedMissing ? <option value={selected}>当前服务不可用</option> : null}
              {providers === null && settings.voiceProvider ? <option value={selected}>{selected}</option> : null}
              {providers?.map((provider) => <option key={providerValue(provider)} value={providerValue(provider)}>{provider.label}</option>)}
            </select>
          </SettingRow>
          <SettingRow label="语音音量"><StoryVolumeControl id="story-voice-volume" label="语音音量" value={settings.voiceVolume} disabled={!settings.voiceProvider} onChange={(value) => updateStoryPreferences({ voiceVolume: value })} /></SettingRow>
          {failure ? <StoryError className="mt-4" message={failure.error} detail={failure.errorDetail} /> : null}
        </div>
      </div>
    </StorySurface>
  );
}
