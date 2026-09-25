import { useAppearancePrefs } from "../useAppearancePrefs";

/**
 * Whether 吟风 appears around the app (设置 › 外观 › 看板娘, on by default).
 * Off, every place she would stand renders its plain, mascot-free version.
 */
export function useMascotEnabled() {
  return useAppearancePrefs().mascot;
}
