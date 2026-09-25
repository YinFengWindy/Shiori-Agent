import { useState } from "react";
import { cx } from "../styles";
import { mascotExpressions, type MascotExpression } from "./mascotExpressions";
import { mascotSprites } from "./mascotSprites";

/*
 * 吟风's three presentation sizes (#362 stage 10). Styles live in
 * `shared/mascot/mascot.css` (imported by the renderer entry, so these stay
 * loadable in node unit tests). All of them are decorative: the line she
 * says is real text next to the figure, never baked into the image.
 */

/**
 * Every expression stacked in one box; a change fades the new face in over
 * the old one, which stays opaque underneath until replaced — all eight
 * sprites share one silhouette, so only the face appears to change
 * (`--duration-quick`, 160ms). The approach of the first-run guide (#377).
 */
export function MascotExpressionStack({ expression, className }: { expression: MascotExpression; className?: string }) {
  // The face being replaced stays visible under the fade (previous-prop pattern).
  const [shown, setShown] = useState({ current: expression, previous: expression });
  if (shown.current !== expression) setShown({ current: expression, previous: shown.current });
  return (
    <div className={cx("mascot-stack", className)}>
      {mascotExpressions.map((key) => (
        <img
          key={key}
          src={mascotSprites[key]}
          alt=""
          draggable={false}
          className="mascot-layer"
          data-layer={key === shown.current ? "current" : key === shown.previous ? "previous" : "hidden"}
        />
      ))}
    </div>
  );
}

/**
 * Half-body sprite, cut just below the waist with a soft fade (startup
 * splash, 设置 › 关于). Its width comes from the caller; the height follows.
 */
export function MascotHalfFigure({ expression, className }: { expression: MascotExpression; className?: string }) {
  return (
    <div className={cx("mascot-half", className)} aria-hidden="true" data-testid="mascot-half" data-expression={expression}>
      <div className="mascot-half-crop">
        <MascotExpressionStack expression={expression} className="mascot-half-stack" />
      </div>
    </div>
  );
}

/**
 * Medium sprite for empty states: the half-body cut at a fixed size range
 * (`--mascot-medium-width`), a single expression.
 */
export function MascotMediumFigure({ expression, className }: { expression: MascotExpression; className?: string }) {
  return (
    <div className={cx("mascot-half mascot-medium", className)} aria-hidden="true" data-testid="mascot-medium" data-expression={expression}>
      <div className="mascot-half-crop">
        <img src={mascotSprites[expression]} alt="" draggable={false} className="mascot-half-stack mascot-single" />
      </div>
    </div>
  );
}

/**
 * Small round face of the given expression — the same framing as her name
 * plate avatar in the first-run guide. `sm` (`--mascot-face-size`) fronts
 * toasts, banners and inline errors; `lg` (`--mascot-face-size-lg`) fronts
 * confirmation dialogs and centred error cards.
 */
export function MascotFaceAvatar({ expression, size = "sm", className }: { expression: MascotExpression; size?: "sm" | "lg"; className?: string }) {
  return (
    <span className={cx("mascot-face", className)} aria-hidden="true" data-testid="mascot-face" data-expression={expression} data-size={size}>
      <img src={mascotSprites[expression]} alt="" draggable={false} />
    </span>
  );
}
