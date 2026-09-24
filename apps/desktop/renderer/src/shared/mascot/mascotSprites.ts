import confused from "../assets/mascot/yinfeng-confused.webp";
import laugh from "../assets/mascot/yinfeng-laugh.webp";
import neutral from "../assets/mascot/yinfeng-neutral.webp";
import pout from "../assets/mascot/yinfeng-pout.webp";
import sad from "../assets/mascot/yinfeng-sad.webp";
import shy from "../assets/mascot/yinfeng-shy.webp";
import smug from "../assets/mascot/yinfeng-smug.webp";
import surprised from "../assets/mascot/yinfeng-surprised.webp";
import type { MascotExpression } from "./mascotExpressions";

/**
 * 吟风's uniform standing sprite, one image per expression. All eight share
 * the exact same alpha mask (826×1213, three-quarter view facing left), so a
 * cross-fade between two of them only changes the face.
 */
export const mascotSprites: Record<MascotExpression, string> = {
  neutral,
  smug,
  laugh,
  shy,
  confused,
  pout,
  sad,
  surprised,
};
