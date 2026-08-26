import type { StoryBeat } from "./types";

/** One renderer-only fragment used to distinguish narration from character speech. */
export type StoryBeatPresentationFragment = {
  kind: "narration" | "dialogue";
  text: string;
};

const legacyDialoguePattern = /“[^”]*”|「[^」]*」|『[^』]*』|"[^"]*"/g;

function defaultFragmentKind(kind: StoryBeat["kind"]): StoryBeatPresentationFragment["kind"] {
  return kind === "dialogue" ? "dialogue" : "narration";
}

function isColonIntroducedQuote(text: string, start: number) {
  let index = start - 1;
  while (index >= 0 && /\s/u.test(text[index] ?? "")) index -= 1;
  return text[index] === ":" || text[index] === "：";
}

/** Splits mixed legacy beat text without changing the committed Story transcript. */
export function getStoryBeatPresentationFragments(beat: Pick<StoryBeat, "kind" | "text">): StoryBeatPresentationFragment[] {
  const matches = [...beat.text.matchAll(legacyDialoguePattern)].filter((match) => isColonIntroducedQuote(beat.text, match.index ?? 0));
  if (matches.length === 0) return [{ kind: defaultFragmentKind(beat.kind), text: beat.text }];

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
