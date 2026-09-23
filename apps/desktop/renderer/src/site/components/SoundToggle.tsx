import { SpeakerSimpleHigh, SpeakerSimpleSlash } from "@phosphor-icons/react";
import { SITE_SOUND_COPY } from "../content/siteCopy";
import { useSound } from "../sound/useSound";

/**
 * Top-right speaker button, the site's master sound switch (muted by
 * default). Its accessible name is always 声音 with on/off in
 * aria-pressed; only the visible tooltip names the action. Placed by
 * `SiteCornerLinks`, just left of the GitHub icon, on every screen.
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
      className="site-icon-button site-corner-chip site-sound-toggle rounded-full p-2.5"
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
