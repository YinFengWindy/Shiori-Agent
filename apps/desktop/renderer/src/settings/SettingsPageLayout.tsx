import { useState, type ReactNode } from "react";
import { cx } from "../shared/styles";
import { SettingsStatusSlotContext } from "./SettingsStatusSlot";

/** Shared surface style for every settings page state. */
export const settingsPageSurfaceClass = "settings-page bg-gradient-app bg-fixed";

type SettingsPageLayoutProps = {
  children: ReactNode;
  feedback?: ReactNode;
};

/**
 * Owns the bounded scroll area for both shared-draft and standalone
 * settings, plus the page corner where `SettingsStatus` publishes the
 * autosave 「已保存」 mark (overlaid on the page rather than in its flow, so
 * it stays visible however far the form is scrolled).
 */
export function SettingsPageLayout({ children, feedback }: SettingsPageLayoutProps) {
  const [statusSlot, setStatusSlot] = useState<HTMLDivElement | null>(null);
  return (
    <SettingsStatusSlotContext.Provider value={statusSlot}>
      <section className={cx(settingsPageSurfaceClass, "relative grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden")} data-testid="settings-page">
        <div ref={setStatusSlot} className="pointer-events-none absolute right-5 top-4 z-[1]" />
        <div>{feedback}</div>
        <div className="relative scrollbar-soft min-h-0 overflow-y-auto px-4 py-8 sm:px-10 lg:px-16 lg:py-10">
          <div className="mx-auto w-full max-w-[840px]">
            {children}
          </div>
        </div>
      </section>
    </SettingsStatusSlotContext.Provider>
  );
}
