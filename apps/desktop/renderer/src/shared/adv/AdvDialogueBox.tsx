interface AdvDialogueBoxProps {
  speaker: string;
  /** Speaker's face for the name plate (a bust crop; the CSS zooms in on the face). */
  avatarSrc: string;
  /** Full text of what's in the box: the current line, or a prompt. */
  text: string;
  /** How much of `text` has been typed out so far. */
  shownChars: number;
  /** Line fully shown and waiting for a click: shows the blinking "next" mark. */
  waiting: boolean;
  /** Placement classes from the owning screen. */
  className?: string;
}

/**
 * The bottom ADV window of the desktop first-run guide: glass panel, name
 * plate with the speaker's avatar and typewriter text. Styles live in
 * `shared/adv/adv.css`.
 *
 * The not-yet-typed remainder is rendered invisibly so the text never
 * reflows while typing. Screen readers get the whole line at once from a
 * polite live region instead of the character-by-character visual text.
 * Clicks on the box fall through (pointer-events: none) to the screen-wide
 * advance surface underneath.
 */
export function AdvDialogueBox({ speaker, avatarSrc, text, shownChars, waiting, className }: AdvDialogueBoxProps) {
  return (
    <section className={["adv-box relative rounded-xl", className].filter(Boolean).join(" ")} aria-label={speaker}>
      <div className="adv-nameplate absolute flex items-center gap-2.5 rounded-full">
        <span className="adv-avatar block h-11 w-11 overflow-hidden rounded-full">
          <img src={avatarSrc} alt="" className="h-full w-full object-cover" />
        </span>
        <span className="font-display text-title">{speaker}</span>
      </div>
      <p className="adv-text" aria-hidden="true">
        <span>{text.slice(0, shownChars)}</span>
        <span className="adv-text-pending">{text.slice(shownChars)}</span>
        {waiting ? <span className="adv-next" /> : null}
      </p>
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {text}
      </p>
    </section>
  );
}
