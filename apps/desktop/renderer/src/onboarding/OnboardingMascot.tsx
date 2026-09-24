import { useState } from "react";
import { mascotExpressions, type MascotExpression } from "../shared/mascot/mascotExpressions";
import { mascotSprites } from "../shared/mascot/mascotSprites";

/** Expressions whose line also moves her body (a bounce / a small hop). */
const bodyReactions: Partial<Record<MascotExpression, string>> = { laugh: "bounce", surprised: "hop" };

/**
 * 吟风 standing on the right. Every expression is stacked; a change fades the
 * new face in over the old one, which stays opaque underneath until replaced —
 * all eight share one silhouette, so only the face appears to change. `cue`
 * increases per spoken line so a repeated laugh bounces again.
 * Motion lives in onboarding.css (with reduced-motion fallbacks).
 */
export function OnboardingMascot({ expression, cue }: { expression: MascotExpression; cue: number }) {
  // The face being replaced stays visible under the fade (previous-prop pattern).
  const [shown, setShown] = useState({ current: expression, previous: expression });
  if (shown.current !== expression) setShown({ current: expression, previous: shown.current });
  const reaction = bodyReactions[expression];
  return (
    <div className="onboarding-mascot" aria-hidden="true">
      <div className="onboarding-mascot-body" data-reaction={reaction} data-cue={cue % 2}>
        {mascotExpressions.map((key) => (
          <img
            key={key}
            src={mascotSprites[key]}
            alt=""
            draggable={false}
            className="onboarding-mascot-layer"
            data-layer={key === shown.current ? "current" : key === shown.previous ? "previous" : "hidden"}
          />
        ))}
      </div>
    </div>
  );
}
