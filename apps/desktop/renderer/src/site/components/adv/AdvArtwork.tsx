import type { AdvArtRef, AdvEventCgKey, AdvSpriteKey } from "../../content/advScript";
import { advEventCgs, advSprites } from "../../content/siteAssets";
import { cx } from "../../siteClassNames";

const SPRITE_KEYS = Object.keys(advSprites) as AdvSpriteKey[];
const EVENT_CG_KEYS = Object.keys(advEventCgs) as AdvEventCgKey[];

interface AdvArtProps {
  art: AdvArtRef;
}

/**
 * 吟风's standing sprite, centre-right over the scene background, behind the
 * dialogue box. Every sprite is stacked so a change cross-fades; while an
 * event CG is up (see `AdvEventCg`) no sprite is active, so the sprite fades
 * out under the CG and back in when the topic ends.
 */
export function AdvSprite({ art }: AdvArtProps) {
  const active = art.kind === "sprite" ? art.key : null;
  return (
    <div className="site-sprite-layer absolute inset-0">
      <div className="site-sprite-stage site-adv-sprite-stage absolute">
        {SPRITE_KEYS.map((key) => (
          <img
            key={key}
            src={advSprites[key].src}
            alt={key === active ? advSprites[key].alt : ""}
            aria-hidden={key !== active}
            className={cx("site-sprite", key === active ? "site-sprite-active" : "site-sprite-inactive")}
          />
        ))}
      </div>
      {/* Soft veil that quiets the room while an event CG is up. */}
      <div className={cx("site-adv-cg-veil absolute inset-0", art.kind === "cg" && "site-adv-cg-veil-active")} aria-hidden="true" />
    </div>
  );
}

/**
 * A topic's event CG: fades in large and framed above the dialogue box in
 * place of the sprite (over `AdvSprite`'s veil), and fades out
 * when the topic ends. Lives in the stage's first grid row (see AdvScreen),
 * so it always fits the space the dialogue box leaves; clicks fall through
 * to the advance surface underneath.
 */
export function AdvEventCg({ art }: AdvArtProps) {
  const active = art.kind === "cg" ? art.key : null;
  return (
    <div className="site-adv-cg-layer pointer-events-none min-h-0">
      {EVENT_CG_KEYS.map((key) => (
        <img
          key={key}
          src={advEventCgs[key].src}
          alt={key === active ? advEventCgs[key].alt : ""}
          aria-hidden={key !== active}
          className={cx("site-adv-cg rounded-xl", key === active ? "site-adv-cg-active" : "site-adv-cg-inactive")}
        />
      ))}
    </div>
  );
}
