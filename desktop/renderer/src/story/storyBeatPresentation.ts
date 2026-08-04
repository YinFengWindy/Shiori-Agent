import type { StoryBeat } from "./types";

/** One renderer-only fragment used to distinguish narration from character speech. */
export type StoryBeatPresentationFragment = {
  kind: "narration" | "dialogue";
  text: string;
};

/** Splits mixed legacy beat text without changing the committed Story transcript. */
export function getStoryBeatPresentationFragments(beat: Pick<StoryBeat, "kind" | "text">): StoryBeatPresentationFragment[] {
  const quotedTextPattern = /“[^”]*”|「[^」]*」|『[^』]*』|"[^"]*"/g;
  const matches = [...beat.text.matchAll(quotedTextPattern)];
  if (matches.length === 0) return [{ kind: beat.kind === "dialogue" ? "dialogue" : "narration", text: beat.text }];

  const fragments: StoryBeatPresentationFragment[] = [];
  let cursor = 0;
  for (const match of matches) {
    const start = match.index ?? 0;
    const narration = beat.text.slice(cursor, start).trim();
    if (narration) fragments.push({ kind: "narration", text: narration });
    const dialogue = match[0].trim();
    if (dialogue) fragments.push({ kind: "dialogue", text: dialogue });
    cursor = start + match[0].length;
  }
  const trailingNarration = beat.text.slice(cursor).trim();
  if (trailingNarration) fragments.push({ kind: "narration", text: trailingNarration });
  return fragments;
}
