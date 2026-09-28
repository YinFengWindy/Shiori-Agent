import { useState, type ReactNode } from "react";
import { cx } from "../styles";

/**
 * Shows and hides a block with a fade plus height change (`.reveal` in
 * styles.css: 0fr → 1fr rows; reduced motion keeps only the fade). While it
 * collapses, the last shown content stays in place, inert, so the block does
 * not empty before it closes; it is dropped once the collapse has finished.
 * A block that starts shown does not animate in, so it never fights the
 * entrance of the dialog or page around it.
 *
 * `className` styles the content box inside the clipped area — put spacing
 * there (e.g. `pt-3`) rather than on a parent grid gap, which a collapsed
 * block would still take up.
 */
export function Reveal({ show, className, children }: { show: boolean; className?: string; children: ReactNode }) {
  const [kept, setKept] = useState<ReactNode>(show ? children : null);
  // Remember what was last shown (adjusting state during render, not in an effect).
  if (show && kept !== children) setKept(children);
  const content = show ? children : kept;
  return <div
    className={cx("reveal", show && "reveal-open")}
    onTransitionEnd={(event) => {
      if (!show && event.target === event.currentTarget) setKept(null);
    }}
  >
    <div inert={!show}>
      {content ? <div className={className}>{content}</div> : null}
    </div>
  </div>;
}
