import { useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cx } from "@shiori/sdk";
import { compactIconButtonClass } from "../shared/styles";
import { contextUsageLabel, type ChatContextStatus } from "./chatContextState";
import { useChatComposerPopover } from "./useChatComposerPopover";

/** A clickable usage ring; the angle always represents capacity, never task progress. */
export function ChatContextRing({ status, busy, notice, unavailable, onCompact }: {
  status: ChatContextStatus | null;
  busy: boolean;
  notice: string;
  unavailable: string;
  onCompact: () => Promise<void>;
}) {
  const button = useRef<HTMLButtonElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const id = useId();
  const usage = contextUsageLabel(status);
  const disabled = Boolean(unavailable) || busy || !status?.can_compact;
  const reason = unavailable || notice || status?.reason || (!status ? "正在读取上下文" : "点击压缩上下文");
  const position = useChatComposerPopover({ open, onClose: () => setOpen(false), triggerRef: button, popoverRef: panel, width: 280, align: "end" });
  return <>
    <button
      ref={button}
      className={cx(compactIconButtonClass, "context-ring-button h-[30px] w-[30px] rounded-full", disabled && "cursor-default text-ink-faint")}
      type="button"
      aria-label={`压缩上下文；${usage.label}；${reason}`}
      aria-describedby={open ? id : undefined}
      aria-disabled={disabled}
      aria-busy={busy}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => { if (document.activeElement !== button.current) setOpen(false); }}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={() => { if (!disabled) void onCompact(); }}
    >
      {/* This is a data visualization rather than an action icon. Unknown has no fill. */}
      <svg className="h-5 w-5 -rotate-90" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" fill="none" stroke="var(--color-border)" strokeWidth="2.5" />
        {usage.ratio !== null ? <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.5" pathLength="100" strokeDasharray={`${Math.min(100, Math.max(0, usage.ratio * 100))} 100`} strokeLinecap="round" /> : null}
        <text x="12" y="12" className="text-caption" transform="rotate(90 12 12)" textAnchor="middle" dominantBaseline="central" fill="currentColor">{busy ? "…" : usage.ratio === null ? "?" : ""}</text>
      </svg>
    </button>
    <span className="sr-only" role="status" aria-live="polite">{notice || unavailable}</span>
    {open && position ? createPortal(
      <div ref={panel} id={id} role="tooltip" className="fixed z-50 w-[280px] rounded-md border border-line bg-surface p-3 text-caption text-ink shadow-soft" style={{ left: position.left, bottom: position.bottom }}>
        <div>{usage.label}</div>
        <div className="mt-1 text-ink-muted">{reason}</div>
      </div>, document.body,
    ) : null}
  </>;
}
