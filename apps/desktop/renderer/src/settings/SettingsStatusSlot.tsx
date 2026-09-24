import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * The page-corner element a settings page reserves for its autosave status.
 * Provided by `SettingsPageLayout`; `null` until that element has mounted.
 */
export const SettingsStatusSlotContext = createContext<HTMLElement | null>(null);

/**
 * Renders a save status (the 「已保存」 mark) into the settings page corner,
 * so a nested page that owns its own autosave — a plugin's config form —
 * reports in the same place as the shared-draft sections do. Renders nothing
 * until the layout's slot exists.
 */
export function SettingsStatus({ children }: { children: ReactNode }) {
  const slot = useContext(SettingsStatusSlotContext);
  return slot ? createPortal(children, slot) : null;
}
