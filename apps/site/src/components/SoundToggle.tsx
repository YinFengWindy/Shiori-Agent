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
import type { SiteDictionary } from "../i18n";

/**
 * Top-right background music switch (React island), muted by default. Its
 * accessible name is always the page language's 背景音乐 (`labels.label`)
 * with the state in `aria-pressed`; the tooltip names the action. The static HTML ships the muted state; a
 * remembered "on" takes over after hydration and starts on the first gesture.
 */
export function SoundToggle({ className, labels }: { className?: string; labels: SiteDictionary["sound"] }) {
  const enabled = useSyncExternalStore(subscribeSound, getSoundEnabled, getServerSoundEnabled);
  useEffect(() => resumeRememberedSoundOnGesture(), []);
  const Icon = enabled ? SpeakerSimpleHighIcon : SpeakerSimpleSlashIcon;

  return (
    <button
      type="button"
      onClick={() => setSoundEnabled(!enabled)}
      aria-pressed={enabled}
      aria-label={labels.label}
      title={enabled ? labels.turnOff : labels.turnOn}
      className={cx(iconButtonClass, className)}
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
