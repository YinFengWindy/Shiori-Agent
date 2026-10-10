import { SpeakerSimpleHighIcon, SpeakerSimpleSlashIcon } from "@phosphor-icons/react";
import { cx, iconButtonClass } from "@yinfengwindy/shiori-sdk";
import { useEffect, useSyncExternalStore } from "react";
import {
  getServerSoundEnabled,
  getSoundEnabled,
  resumeRememberedSoundOnGesture,
  setSoundEnabled,
  subscribeSound,
} from "../lib/siteSound";

/**
 * Top-right background music switch (React island), muted by default. Its
 * accessible name is always 背景音乐 with the state in `aria-pressed`; the
 * tooltip names the action. The static HTML ships the muted state; a
 * remembered "on" takes over after hydration and starts on the first gesture.
 */
export function SoundToggle({ className }: { className?: string }) {
  const enabled = useSyncExternalStore(subscribeSound, getSoundEnabled, getServerSoundEnabled);
  useEffect(() => resumeRememberedSoundOnGesture(), []);
  const Icon = enabled ? SpeakerSimpleHighIcon : SpeakerSimpleSlashIcon;

  return (
    <button
      type="button"
      onClick={() => setSoundEnabled(!enabled)}
      aria-pressed={enabled}
      aria-label="背景音乐"
      title={enabled ? "关闭背景音乐" : "播放背景音乐"}
      className={cx(iconButtonClass, className)}
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
