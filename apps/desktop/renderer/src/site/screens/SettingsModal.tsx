import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";
import { SITE_SETTINGS_CLOSE_LABEL, SITE_SETTINGS_PLACEHOLDER, SITE_SETTINGS_TITLE } from "../content/siteCopy";

interface SettingsModalProps {
  onClose: () => void;
}

/**
 * Placeholder settings dialog (BGM/SFX volume, text speed land here in
 * #348). Esc is handled by `useSiteScreen`; this component only owns the
 * close button and initial focus.
 */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  return (
    <div className="site-modal-backdrop fixed inset-0 z-50 grid place-items-center px-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-settings-title"
        className="site-panel w-full max-w-sm rounded-xl px-6 py-6"
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
        <p className="mt-4 text-body text-site-ink-muted">{SITE_SETTINGS_PLACEHOLDER}</p>
      </div>
    </div>
  );
}
