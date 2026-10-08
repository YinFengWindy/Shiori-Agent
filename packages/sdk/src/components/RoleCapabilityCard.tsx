import type { ReactNode } from "react";
import { cardClass, cx } from "../styles";
import { CapabilitySettingsDialog } from "./CapabilitySettingsDialog";
import type { RoleCapabilityStatus, RoleCapabilityTone } from "../roleCapability";

const toneClass: Record<RoleCapabilityTone, string> = {
  on: "bg-success-soft text-success-text",
  off: "bg-surface-soft text-ink-muted",
  attention: "bg-warning-soft text-warning-text",
};

/** The status pill of a role capability; also used beside a section switch (主动推送). */
export function RoleCapabilityBadge({ status }: { status: RoleCapabilityStatus }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-caption", toneClass[status.tone])} data-tone={status.tone}>
      {status.label}
    </span>
  );
}

type RoleCapabilityCardProps = {
  icon: ReactNode;
  title: string;
  status: RoleCapabilityStatus;
  /** The card's switch (or other control), at the right end of the title row. */
  control?: ReactNode;
  /**
   * The capability's secondary settings (runtime API 3.1.11, #719). When
   * given, a ⚙ button after the control opens them in a centred dialog titled
   * by `title`; they mount only while it is open. Pass an empty container to
   * offer the dialog before it has fields.
   */
  settings?: ReactNode;
  /** Extra rows under the title row, e.g. the voice parameters. */
  children?: ReactNode;
  className?: string;
  "data-testid"?: string;
};

/**
 * The one card shape for every role capability on the 能力 tab, host-owned
 * (NSFW memory, voice) and plugin-contributed (desktop pet, scene CG) alike:
 * icon, title, a status badge that says whether it really works, the switch and,
 * for capabilities with more to configure, the ⚙ of their settings dialog.
 */
export function RoleCapabilityCard({ icon, title, status, control, settings, children, className, ...rest }: RoleCapabilityCardProps) {
  return (
    <div className={cx(cardClass, "grid content-start gap-4 p-5", className)} data-testid={rest["data-testid"]}>
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-accent-softer text-accent-text" aria-hidden="true">
          {icon}
        </span>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <span className="truncate text-body font-semibold text-ink">{title}</span>
          <RoleCapabilityBadge status={status} />
        </div>
        {control}
        {settings ? <CapabilitySettingsDialog title={title}>{settings}</CapabilitySettingsDialog> : null}
      </div>
      {children}
    </div>
  );
}
