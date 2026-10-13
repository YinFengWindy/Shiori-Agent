import type { MascotExpression } from "../../../desktop/renderer/src/shared/mascot/mascotExpressions";

/** Event CGs the narrative can show beside 吟风; `siteAssets.narrativeCgs` maps each key to an image. */
export type NarrativeCgKey = "cg-3" | "cg-7" | "cg-8" | "cg-9" | "cg-10" | "topic-1" | "topic-2" | "topic-3";

/** How a line of the home page narrative is staged: 吟风's face while saying it, and an optional event CG. */
interface NarrativeStaging {
  /** Stable anchor of the line (its element's `id`, `/#<id>`), also the key of its words in each dictionary. */
  readonly id: string;
  readonly expression: MascotExpression;
  /** Event CG framed beside her; the previous CG is not carried over to a line without one. */
  readonly cg?: NarrativeCgKey;
}

/*
 * The home page narrative (#771): 吟风, Shiori 的看板娘 (a playful little
 * devil, same voice as the old site's ADV script), introduces herself and
 * then the product. One line per scroll step. What she says is in the
 * dictionaries (i18n/zh.ts, i18n/en.ts, keyed by `id`); every claim must
 * match README.md, and each line stays short (≤ 40 characters in Chinese)
 * so it fits the dialogue box on a phone in two or three lines.
 *
 * Each line's `id` is its anchor (#806): the language switch carries the
 * line on stage across (`/en/#remembers`), and the narrative opens on it
 * (`narrativeAnchorStep`, lib/narrativeModel.ts). Keep the ids once
 * published, and clear of the page's other ids (the showcase's feature
 * ids, `download`).
 */
const lines = [
  { id: "arrival", expression: "smug" },
  { id: "introduction", expression: "laugh" },
  { id: "companion", expression: "neutral" },
  { id: "characters", expression: "neutral", cg: "cg-8" },
  { id: "remembers", expression: "smug", cg: "cg-9" },
  { id: "affinity", expression: "shy", cg: "cg-7" },
  { id: "comes-to-find-you", expression: "pout", cg: "topic-2" },
  { id: "everywhere", expression: "laugh", cg: "topic-2" },
  { id: "gets-things-done", expression: "surprised", cg: "cg-3" },
  { id: "story-mode", expression: "smug", cg: "topic-3" },
  { id: "desktop-pet", expression: "neutral", cg: "cg-10" },
  { id: "plugins-on-demand", expression: "confused", cg: "topic-1" },
  { id: "take-me-home", expression: "sad" },
  { id: "see-you", expression: "laugh" },
] as const satisfies readonly NarrativeStaging[];

/** A narrative line's id: its anchor and its key in the dictionaries. */
export type NarrativeLineId = (typeof lines)[number]["id"];

/** One line of the home page narrative as staged; its words are the dictionaries' `narrative.lines[id]`. */
export interface NarrativeLine extends NarrativeStaging {
  readonly id: NarrativeLineId;
}

/** The narrative's lines, in order. */
export const NARRATIVE_LINES: readonly NarrativeLine[] = lines;
