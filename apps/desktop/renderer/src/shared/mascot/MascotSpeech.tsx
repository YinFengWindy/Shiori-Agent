import type { ReactNode } from "react";
import { cx } from "../styles";
import { MascotMediumFigure } from "./MascotFigure";
import { mascotName } from "./mascotExpressions";
import type { MascotLine } from "./mascotLines";

/**
 * What 吟风 says, in a small glass speech bubble under her name. `tail`
 * points the bubble at her: toward the figure on the left, right or top.
 * The text is a live region only when `live` is set (a line that changes in
 * place, e.g. 关于's click-for-another-line); static lines are plain text.
 */
export function MascotSpeechBubble({ line, tail, live = false, className }: {
  line: MascotLine;
  tail: "left" | "right" | "top";
  live?: boolean;
  className?: string;
}) {
  return (
    <p className={cx("mascot-bubble", className)} data-tail={tail} data-testid="mascot-line" aria-live={live ? "polite" : undefined}>
      <span className="mascot-bubble-name">{mascotName}</span>
      <span className="mascot-bubble-text">{line.text}</span>
    </p>
  );
}

/**
 * An empty state fronted by 吟风: her medium sprite, her line and the view's
 * own actions. `side` puts her beside the bubble (wide areas: the roles
 * page); `stack` puts her above it (narrow areas: the chat sidebar, search).
 * Callers render their plain empty state instead when the mascot is off.
 */
export function MascotEmptyState({ line, layout, size = layout === "stack" ? "compact" : "medium", children, className, testId }: {
  line: MascotLine;
  layout: "side" | "stack";
  /** Figure width: `medium` (--mascot-medium-width, default beside) or `compact` (--mascot-compact-width, default stacked). */
  size?: "medium" | "compact";
  /** The empty state's action buttons, if any. */
  children?: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <div className={cx("mascot-empty mascot-enter", className)} data-layout={layout} data-size={size} data-testid={testId}>
      <MascotMediumFigure expression={line.expression} className="mascot-empty-figure" />
      <div className="mascot-empty-body">
        <MascotSpeechBubble line={line} tail={layout === "side" ? "left" : "top"} />
        {children ? <div className="mascot-empty-actions">{children}</div> : null}
      </div>
    </div>
  );
}
