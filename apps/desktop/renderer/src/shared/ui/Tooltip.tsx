import type React from "react";
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";

/** Hover delay before the first tooltip in a group shows; neighbours then open at once. */
export const tooltipDelayMs = 450;

/** Glass bubble shared by every tooltip; motion comes from `motion-popup` (reduced-motion safe). */
export const tooltipPopupClass =
  "motion-popup surface-glass-strong pointer-events-none flex max-w-[260px] items-center gap-2 rounded-md px-2.5 py-1.5 text-caption text-ink";

/** Keyboard hint chip inside a tooltip (e.g. 「Ctrl+1」). */
export const tooltipShortcutClass =
  "rounded-sm border border-line-soft bg-white/70 px-1.5 py-px font-sans text-caption leading-4 text-ink-muted";

type TooltipProps = {
  /** Short name of the control. Screen readers get it from the trigger's own aria-label, not from here. */
  label: string;
  /** Optional keyboard shortcut shown as a chip next to the label. */
  shortcut?: string;
  side?: "top" | "right" | "bottom" | "left";
  disabled?: boolean;
  /**
   * The trigger. Must be a single element that forwards props and ref (a DOM
   * button does); Base UI merges hover / focus handlers into it. Use
   * `aria-disabled` instead of `disabled` on a trigger that must still explain
   * itself: a disabled button receives no pointer or focus events.
   */
  children: React.ReactElement;
};

/**
 * Brand tooltip: glass bubble with an optional shortcut chip. Opens on hover
 * after `tooltipDelayMs` and on keyboard focus (focus-visible only), closes
 * on click, Escape or leave. Place `TooltipProvider` once near the root so
 * adjacent tooltips (the nav rail) open without re-waiting.
 */
export function Tooltip({ label, shortcut, side = "right", disabled, children }: TooltipProps) {
  return (
    <TooltipPrimitive.Root disabled={disabled}>
      <TooltipPrimitive.Trigger render={children} />
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Positioner side={side} sideOffset={8} collisionPadding={8} className="z-[120]">
          <TooltipPrimitive.Popup className={tooltipPopupClass} data-testid="tooltip">
            <span className="min-w-0 break-words">{label}</span>
            {shortcut ? <kbd className={tooltipShortcutClass}>{shortcut}</kbd> : null}
          </TooltipPrimitive.Popup>
        </TooltipPrimitive.Positioner>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/** Shares one open delay (and the "already warm" grouping) across every tooltip below it. */
export function TooltipProvider({ children }: { children: React.ReactNode }) {
  return (
    <TooltipPrimitive.Provider delay={tooltipDelayMs}>
      {children}
    </TooltipPrimitive.Provider>
  );
}

