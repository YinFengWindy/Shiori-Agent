import type { MascotExpression } from "../shared/mascot/mascotExpressions";
import { MascotExpressionStack } from "../shared/mascot/MascotFigure";

/** Expressions whose line also moves her body (a bounce / a small hop). */
const bodyReactions: Partial<Record<MascotExpression, string>> = { laugh: "bounce", surprised: "hop" };

/**
 * 吟风 standing on the right, her faces cross-fading through the shared
 * expression stack (`shared/mascot/MascotFigure`). `cue` increases per
 * spoken line so a repeated laugh bounces again.
 * Motion lives in onboarding.css (with reduced-motion fallbacks).
 */
export function OnboardingMascot({ expression, cue }: { expression: MascotExpression; cue: number }) {
  const reaction = bodyReactions[expression];
  return (
    <div className="onboarding-mascot" aria-hidden="true">
      <div className="onboarding-mascot-body" data-reaction={reaction} data-cue={cue % 2}>
        <MascotExpressionStack expression={expression} className="onboarding-mascot-stack" />
      </div>
    </div>
  );
}
