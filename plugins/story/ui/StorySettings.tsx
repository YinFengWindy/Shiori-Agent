import { ArrowLeft } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { StorySegmentedControl, StoryToggle } from "./StorySettingsControls";
import { StorySurface } from "./StorySurface";
import { updateStoryPreferences, useStoryPreferences, type StoryPace } from "./storyPreferences";
import { storyIconButtonClass, storyPageHeaderClass, storyPageTitleClass, storyGutterClass } from "./storyStyles";
import type { StoryMenuBackground } from "./useStoryMenuBackground";

type StorySettingsProps = { background?: StoryMenuBackground; sharedBackdrop?: boolean; onBack: () => void };

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

/** Renders the Story playback preferences; every change applies immediately to the running Story. */
export function StorySettings({ background, sharedBackdrop = false, onBack }: StorySettingsProps) {
  const settings = useStoryPreferences();

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
        </div>
      </div>
    </StorySurface>
  );
}
