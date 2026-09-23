import { SpeakerSimpleHigh, SpeakerSimpleSlash } from "@phosphor-icons/react";
import { SITE_SOUND_COPY } from "../content/siteCopy";
import { useSound } from "../sound/useSound";

/**
 * Top-right speaker button, the site's master sound switch (muted by
 * default). Its accessible name is always 声音 with on/off in
 * aria-pressed; only the visible tooltip names the action. Fixed so it stays put across screens; on the title screen it
 * sits just left of the GitHub corner icon (see `.site-sound-toggle`).
 */
export function SoundToggle() {
  const { soundEnabled, toggleSound } = useSound();
  const Icon = soundEnabled ? SpeakerSimpleHigh : SpeakerSimpleSlash;

  return (
    <button
      type="button"
      onClick={toggleSound}
      aria-pressed={soundEnabled}
      aria-label={SITE_SOUND_COPY.label}
      title={soundEnabled ? SITE_SOUND_COPY.disableTitle : SITE_SOUND_COPY.enableTitle}
      className="site-icon-button site-sound-toggle fixed z-20 rounded-md p-2"
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
