import type { ReactNode } from "react";
import { cx } from "../shared/styles";

/** Shared surface style for every settings page state. */
export const settingsPageSurfaceClass = "settings-page bg-gradient-app bg-fixed";

type SettingsPageLayoutProps = {
  children: ReactNode;
  feedback?: ReactNode;
};

/** Owns the bounded scroll area for both shared-draft and standalone settings. */
export function SettingsPageLayout({ children, feedback }: SettingsPageLayoutProps) {
  return (
    <section className={cx(settingsPageSurfaceClass, "relative grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden")} data-testid="settings-page">
      <div>{feedback}</div>
      <div className="relative scrollbar-soft min-h-0 overflow-y-auto px-4 py-8 sm:px-10 lg:px-16 lg:py-10">
        <div className="mx-auto w-full max-w-[840px]">
          {children}
        </div>
      </div>
    </section>
  );
}
