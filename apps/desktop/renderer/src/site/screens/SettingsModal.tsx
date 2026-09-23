import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";
import { TextSpeedPicker } from "../components/settings/TextSpeedPicker";
import { TextSpeedPreview } from "../components/settings/TextSpeedPreview";
import { VolumeSlider } from "../components/settings/VolumeSlider";
import { SITE_SETTINGS_CLOSE_LABEL, SITE_SETTINGS_COPY, SITE_SETTINGS_TITLE } from "../content/siteCopy";
import { useDialogFocus } from "../hooks/useDialogFocus";
import { TEXT_SPEED_MS_PER_CHAR } from "../prefs/sitePrefs";
import { useSitePrefs } from "../prefs/useSitePrefs";
import { useSound } from "../sound/useSound";

interface SettingsModalProps {
  onClose: () => void;
}

/**
 * Settings dialog: BGM / SFX volume and text speed, saved immediately via
 * `useSitePrefs` (the ADV typewriter picks up a new speed on its next
 * frame). Volumes apply live via `SoundProvider`; moving the SFX slider
 * plays a sample blip. Esc and right-click are handled by `useSiteScreen`.
 */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const { prefs, update } = useSitePrefs();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useDialogFocus(dialogRef, closeButtonRef);
  const { playSfx, previewSfx } = useSound();
  useEffect(() => {
    playSfx("open");
    return () => playSfx("close");
  }, [playSfx]);

  return (
    <div className="site-modal-backdrop fixed inset-0 z-50 grid place-items-center px-4" onClick={onClose}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-settings-title"
        className="site-panel site-settings w-full max-w-sm rounded-xl px-6 py-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4">
          <h2 id="site-settings-title" className="font-display text-title text-site-ink">
            {SITE_SETTINGS_TITLE}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label={SITE_SETTINGS_CLOSE_LABEL}
            className="site-icon-button rounded-md p-1.5"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="mt-5 flex flex-col gap-5">
          <VolumeSlider id="site-bgm-volume" label={SITE_SETTINGS_COPY.bgmVolume} value={prefs.bgmVolume} onChange={(bgmVolume) => update({ bgmVolume })} />
          <VolumeSlider id="site-sfx-volume" label={SITE_SETTINGS_COPY.sfxVolume} value={prefs.sfxVolume} onChange={(sfxVolume) => {
              update({ sfxVolume });
              previewSfx(sfxVolume);
            }} />
          <div className="flex flex-col gap-3">
            <TextSpeedPicker value={prefs.textSpeed} onChange={(textSpeed) => update({ textSpeed })} />
            <TextSpeedPreview key={prefs.textSpeed} text={SITE_SETTINGS_COPY.textSpeedPreview} msPerChar={TEXT_SPEED_MS_PER_CHAR[prefs.textSpeed]} />
          </div>
        </div>
      </div>
    </div>
  );
}
