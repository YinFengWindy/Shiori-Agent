import { SHOWCASE_CLIP_IDS, type ShowcaseClipId } from "../../site/src/content/showcase";

/**
 * The clip ids a render script was asked for on its command line (every
 * clip when none is given); an unknown id is an error.
 */
export function clipIdsFromArgs(args: readonly string[]): readonly ShowcaseClipId[] {
  const isClipId = (id: string): id is ShowcaseClipId => (SHOWCASE_CLIP_IDS as readonly string[]).includes(id);
  const unknown = args.filter((id) => !isClipId(id));
  if (unknown.length > 0) throw new Error(`unknown clip id: ${unknown.join(", ")}`);
  return args.length > 0 ? args.filter(isClipId) : SHOWCASE_CLIP_IDS;
}
