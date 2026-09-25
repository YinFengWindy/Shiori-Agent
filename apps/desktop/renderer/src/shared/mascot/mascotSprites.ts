import type { MascotExpression } from "./mascotExpressions";

/*
 * Resolved with `new URL(…, import.meta.url)` rather than imported: Vite
 * emits the files the same way, and the plain Node test runner (which has no
 * loader for .webp) can load every component that shows her.
 */
const neutral = new URL("../assets/mascot/yinfeng-neutral.webp", import.meta.url).href;
const smug = new URL("../assets/mascot/yinfeng-smug.webp", import.meta.url).href;
const laugh = new URL("../assets/mascot/yinfeng-laugh.webp", import.meta.url).href;
const shy = new URL("../assets/mascot/yinfeng-shy.webp", import.meta.url).href;
const confused = new URL("../assets/mascot/yinfeng-confused.webp", import.meta.url).href;
const pout = new URL("../assets/mascot/yinfeng-pout.webp", import.meta.url).href;
const sad = new URL("../assets/mascot/yinfeng-sad.webp", import.meta.url).href;
const surprised = new URL("../assets/mascot/yinfeng-surprised.webp", import.meta.url).href;

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
