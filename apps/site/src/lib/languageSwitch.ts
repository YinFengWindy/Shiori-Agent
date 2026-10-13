/*
 * Where the language switch leads on the home page (#806): the other
 * language's home page at the same place — the narrative's line on show,
 * its download call, or the showcase block being read — by that place's
 * anchor (`/en/#remembers`). The narrative's own steps come from
 * `narrativeStepAnchor` (narrativeModel.ts); this picks the place among
 * elements laid out in the page flow. Pure, with no DOM.
 */

/** An anchored element of the page: its id and its top edge relative to the viewport top (px). */
export interface AnchoredPlace {
  readonly id: string;
  readonly top: number;
}

/**
 * The anchor of the place being read: the last of `places` (in page order)
 * whose top has risen to the reading `line` (px below the viewport top), or
 * the first one while none has yet.
 */
export function anchorAtReadingLine(places: readonly AnchoredPlace[], line: number): string {
  const [first] = places;
  if (!first) throw new Error("no anchored place to read");
  if (!Number.isFinite(line)) throw new Error(`line must be finite, got ${line}`);
  let current = first.id;
  for (const place of places) {
    if (place.top <= line) current = place.id;
  }
  return current;
}

/**
 * `href` (a site path, possibly with a hash already) pointing at `anchor`
 * instead: the switch's static target with the reader's place added.
 */
export function hrefWithAnchor(href: string, anchor: string): string {
  const hashAt = href.indexOf("#");
  const base = hashAt >= 0 ? href.slice(0, hashAt) : href;
  return `${base}#${encodeURIComponent(anchor)}`;
}
