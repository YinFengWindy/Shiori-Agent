import commonEmojiEntries from "./common_emojis.json";

/** Shared emoji entries exposed to both the desktop composer and role replies. */
export const commonChatEmojis = commonEmojiEntries.map((entry) => entry.value) as readonly string[];

/** Caret placement returned after inserting an emoji into the draft. */
export type ChatEmojiInsertion = {
  value: string;
  selectionStart: number;
  selectionEnd: number;
};

function clampSelectionIndex(value: number, textLength: number): number {
  if (!Number.isFinite(value)) {
    return textLength;
  }
  return Math.min(Math.max(0, value), textLength);
}

/** Inserts one emoji at the current selection so the composer can preserve caret placement. */
export function insertEmojiIntoChatDraft(
  draft: string,
  emoji: string,
  selectionStart?: number | null,
  selectionEnd?: number | null,
): ChatEmojiInsertion {
  const start = clampSelectionIndex(selectionStart ?? draft.length, draft.length);
  const end = clampSelectionIndex(selectionEnd ?? start, draft.length);
  const rangeStart = Math.min(start, end);
  const rangeEnd = Math.max(start, end);
  const value = `${draft.slice(0, rangeStart)}${emoji}${draft.slice(rangeEnd)}`;
  const caret = rangeStart + emoji.length;
  return {
    value,
    selectionStart: caret,
    selectionEnd: caret,
  };
}
