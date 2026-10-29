import type { ReactNode } from "react";
import { cardClass, cx } from "@yinfengwindy/shiori-sdk";

type AffectionCardProps = {
  /** Small heading, also the section's accessible name. */
  title: string;
  /** Status shown opposite the heading (e.g. the autosave indicator). */
  aside?: ReactNode;
  testId?: string;
  children: ReactNode;
};

/** The one card style of the 「好感度」 tab's sections (好感 / 变化 / 阶段语气). */
export function AffectionCard({ title, aside, testId, children }: AffectionCardProps) {
  return <section className={cx(cardClass, "grid content-start gap-4 px-5 py-4")} aria-label={title} data-testid={testId}>
    <div className="flex min-h-6 items-center justify-between gap-3">
      <h3 className="m-0 text-body-sm font-semibold text-ink-muted">{title}</h3>
      {aside}
    </div>
    {children}
  </section>;
}
