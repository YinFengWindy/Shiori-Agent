import type { ReactNode } from "react";
import { avatarImage } from "../../content/siteAssets";

interface AdvDialogueBoxProps {
  speaker: string;
  /** Full text of what's in the box: the current line, or the choice prompt. */
  text: string;
  /** How much of `text` has been typed out so far. */
  shownChars: number;
  /** Line fully shown and waiting for a click: shows the blinking "next" mark. */
  waiting: boolean;
  /** The box's control buttons (自动/跳过/记录/…). */
  controls: ReactNode;
}

/**
 * The bottom ADV window: glass panel, name plate with 吟风's avatar,
 * typewriter text and the control row.
 *
 * The not-yet-typed remainder is rendered invisibly so the text never
 * reflows while typing. Screen readers get the whole line at once from a
 * polite live region instead of the character-by-character visual text.
 * Clicks on the box itself fall through (pointer-events: none) to the
 * screen-wide advance surface underneath; only the controls take clicks.
 */
export function AdvDialogueBox({ speaker, text, shownChars, waiting, controls }: AdvDialogueBoxProps) {
  return (
    <section className="site-adv-box relative rounded-xl" aria-label={speaker}>
      <div className="site-adv-nameplate absolute flex items-center gap-2.5 rounded-full">
        <span className="site-adv-avatar block h-11 w-11 overflow-hidden rounded-full">
          <img src={avatarImage.src} alt="" className="h-full w-full object-cover" />
        </span>
        <span className="font-display text-title">{speaker}</span>
      </div>
      <p className="site-adv-text" aria-hidden="true">
        <span>{text.slice(0, shownChars)}</span>
        <span className="site-adv-text-pending">{text.slice(shownChars)}</span>
        {waiting ? <span className="site-adv-next" /> : null}
      </p>
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {text}
      </p>
      <div className="site-adv-controls flex flex-wrap items-center justify-end gap-1">{controls}</div>
    </section>
  );
}
