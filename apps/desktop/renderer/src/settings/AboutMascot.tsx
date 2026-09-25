import type { ReactNode } from "react";
import type { DesktopUpdateState } from "../../../src/updateContract.js";
import { MascotHalfFigure } from "../shared/mascot/MascotFigure";
import { mascotName } from "../shared/mascot/mascotExpressions";
import { MascotSpeechBubble } from "../shared/mascot/MascotSpeech";
import { useAboutMascotLine } from "./aboutMascotLine";

/**
 * 设置 › 关于 with 吟风 (#362 stage 10): the version card and her line on
 * the left, her half-body on the right. Clicking her draws another line
 * (and with it another face, cross-faded); the update check's outcome is
 * announced in her line too. Her lines are an owner-approved exception to
 * 「不写叙述文字」. Styles: `.about-mascot*` in styles.css.
 */
export function AboutMascot({ phase, children }: { phase: DesktopUpdateState["phase"] | undefined; children: ReactNode }) {
  const { line, next } = useAboutMascotLine(phase);
  return (
    <div className="about-mascot" data-testid="about-mascot">
      <div className="about-mascot-main">
        {children}
        <MascotSpeechBubble line={line} tail="right" live className="mascot-enter" />
      </div>
      <button type="button" className="about-mascot-figure mascot-enter" aria-label={mascotName} onClick={next}>
        <MascotHalfFigure expression={line.expression} />
      </button>
    </div>
  );
}
