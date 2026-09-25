import { WarningCircle, X, type Icon } from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";
import { MascotFaceAvatar } from "../mascot/MascotFigure";
import { useMascotCameoAllowed } from "../mascot/MascotOnStage";
import { MascotSpeechBubble } from "../mascot/MascotSpeech";
import { inlineErrorLines, type InlineErrorPersona } from "../mascot/mascotLines";
import { compactPressableClass, cx } from "../styles";
import { FeedbackDetail } from "./FeedbackDetail";

/** Props of the shared in-page error block. */
export type InlineErrorProps = {
  /** The original, factual message; always shown, persona or not. */
  message: string;
  /** Heading of a `card` (e.g. 「生成失败」); rows and strips have none. */
  title?: string;
  /** Technical cause folded behind 「详情」. */
  detail?: string;
  /** The way out (retry, reload, open settings …), placed after the text. */
  actions?: ReactNode;
  /**
   * Which of 吟风's inline-error lines fronts the block (default `generic`),
   * or `false` for a plain block. She also stays out when the 看板娘 is off
   * or she already stands in this subtree (`MascotOnStage`).
   */
  persona?: InlineErrorPersona | false;
  /**
   * `row`: a compact bordered block inside a form or list. `strip`: a
   * full-width band pinned to a container's edge (a card footer). `card`:
   * a centred glass card that takes over an empty area.
   */
  layout?: "row" | "strip" | "card";
  /** Glyph of the plain block (default the warning circle). */
  glyph?: Icon;
  /** Tint of the plain glyph: `accent` for a problem the user fixes in settings rather than a failure. */
  glyphTone?: "danger" | "accent";
  /**
   * `alert` interrupts assistive tech (default); `status` for results the
   * user just asked for; `false` inside a container that already is a live region.
   */
  role?: "alert" | "status" | false;
  /** Adds a close button (cards). */
  onDismiss?: () => void;
  className?: string;
  testId?: string;
};

const glyphToneClass = {
  danger: "text-danger-text",
  accent: "text-accent-text",
} as const;

const cardGlyphBadgeClass = {
  danger: "bg-danger-soft text-danger-text",
  accent: "bg-accent-softer text-accent-text",
} as const;

const layoutClass = {
  row: "flex items-start gap-2.5 rounded-md border border-[var(--danger-300)] bg-danger-soft px-3 py-2.5 text-body-sm",
  strip: "flex items-start gap-2.5 border-t border-line-soft bg-danger-soft/60 px-5 py-2 text-body-sm",
  card: "surface-glass-strong relative grid w-full max-w-[420px] justify-items-center gap-3 rounded-xl px-6 py-7 text-center",
} as const;

/**
 * The one in-page error block (#362 follow-up): settings save / load
 * failures, the model connection test, the chat error row, the first-run
 * guide's error areas, plugin cards … With the 看板娘 on, 吟风's face and
 * her line lead it and the original message follows; off, it is the plain
 * block with a warning glyph. Her lines are the owner-approved exception to
 * AGENTS.md 「前端页面不要产生对功能进行叙述的文字」 (see mascotLines.ts).
 * Plugins reach it as `PluginHostServices.ui.InlineError`.
 */
export function InlineError({
  message,
  title,
  detail,
  actions,
  persona = "generic",
  layout = "row",
  glyph: Glyph = WarningCircle,
  glyphTone = "danger",
  role = "alert",
  onDismiss,
  className,
  testId,
}: InlineErrorProps) {
  const [detailOpen, setDetailOpen] = useState(false);
  const cameo = useMascotCameoAllowed();
  const line = cameo && persona ? inlineErrorLines[persona] : null;
  const detailFold = detail ? <FeedbackDetail detail={detail} open={detailOpen} onToggle={() => setDetailOpen((current) => !current)} /> : null;
  const dismiss = onDismiss ? (
    <button
      className={cx(compactPressableClass, "grid h-7 w-7 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink", layout === "card" && "absolute right-3 top-3")}
      type="button"
      aria-label="关闭"
      onClick={onDismiss}
    >
      <X className="h-4 w-4" aria-hidden="true" />
    </button>
  ) : null;

  if (layout === "card") {
    return (
      <div className={cx(layoutClass.card, className)} role={role || undefined} data-testid={testId} data-persona={line ? persona : undefined}>
        {dismiss}
        {/* Plain: the glyph badge heads the card. With her: title first, then she speaks beside her face (as in ConfirmDialog). */}
        {line ? null : (
          <span className={cx("grid h-12 w-12 place-items-center rounded-full", cardGlyphBadgeClass[glyphTone])} aria-hidden="true">
            <Glyph className="h-6 w-6" weight="duotone" />
          </span>
        )}
        {title ? <span className={cx("font-display text-title-sm text-ink", line && "px-6")}>{title}</span> : null}
        {line ? (
          <div className="flex w-full items-start gap-3 text-left">
            <MascotFaceAvatar expression={line.expression} size="lg" />
            <MascotSpeechBubble line={line} tail="left" className="min-w-0 flex-1" />
          </div>
        ) : null}
        {message ? <span className="max-h-28 overflow-y-auto break-words text-body-sm text-ink-muted [overflow-wrap:anywhere]">{message}</span> : null}
        {detailFold ? <span className="grid w-full justify-items-center gap-1">{detailFold}</span> : null}
        {actions ? <div className="mt-1 flex flex-wrap justify-center gap-2">{actions}</div> : null}
      </div>
    );
  }

  return (
    <div className={cx(layoutClass[layout], className)} role={role || undefined} data-testid={testId} data-persona={line ? persona : undefined}>
      {line ? (
        <MascotFaceAvatar expression={line.expression} className="-my-0.5" />
      ) : (
        <Glyph className={cx("mt-0.5 h-4 w-4 shrink-0", glyphToneClass[glyphTone])} weight="fill" aria-hidden="true" />
      )}
      <span className="grid min-w-0 flex-1 gap-0.5">
        {/* Her line is the first sentence; the original message follows it. */}
        {line ? <span className="break-words font-medium leading-5 text-ink" data-testid="inline-error-line">{line.text}</span> : null}
        <span className="break-words leading-5 text-danger-text [overflow-wrap:anywhere]">{message}</span>
        {detailFold}
      </span>
      {actions ? <span className="flex shrink-0 items-center gap-1 self-center">{actions}</span> : null}
      {dismiss}
    </div>
  );
}
