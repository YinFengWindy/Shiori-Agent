import { useEffect, useState } from "react";
import type { SettingsFormData } from "../../../src/bridge/shared";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";

/**
 * Reads the saved desktop settings once per mount, for role panels whose
 * display depends on a global switch (voice output, dev mode). Null until
 * the read resolves; a failed read is reported and stays null, so callers
 * treat the global state as unknown rather than guessing.
 */
export function useSettingsSnapshot(): SettingsFormData | null {
  const [settings, setSettings] = useState<SettingsFormData | null>(null);

  useEffect(() => {
    let cancelled = false;
    window.miraDesktop.readSettings()
      .then((snapshot) => {
        if (!cancelled) setSettings(snapshot.formData);
      })
      .catch((error: unknown) => {
        if (!cancelled) feedback.error(`设置读取失败：${errorMessage(error)}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return settings;
}
