import { useCallback, useEffect, useState } from "react";

type TypewriterProgress = { key: string; count: number };

/** Progressive reveal of one text fragment, restarted whenever `resetKey` changes. */
export type StoryTypewriter = {
  /** The revealed prefix; the rest of the text is still hidden. */
  visibleText: string;
  hiddenText: string;
  complete: boolean;
  /** Reveals the whole fragment at once (a click or key while it is still typing). */
  finish: () => void;
};

/**
 * Reveals `text` at `charactersPerSecond`, or all at once when it is null.
 * Characters are counted as code points so emoji and CJK never split.
 */
export function useStoryTypewriter(text: string, resetKey: string, charactersPerSecond: number | null): StoryTypewriter {
  const characters = Array.from(text);
  const length = characters.length;
  const [progress, setProgress] = useState<TypewriterProgress>({ key: resetKey, count: 0 });
  const count = charactersPerSecond === null ? length : progress.key === resetKey ? Math.min(progress.count, length) : 0;

  useEffect(() => {
    if (charactersPerSecond === null || length === 0) return;
    let frame = 0;
    let startedAt: number | null = null;
    const tick = (now: number) => {
      startedAt ??= now;
      const due = Math.min(length, Math.floor(((now - startedAt) / 1000) * charactersPerSecond) + 1);
      setProgress((current) => {
        const shown = current.key === resetKey ? current.count : 0;
        return due <= shown ? current : { key: resetKey, count: due };
      });
      if (due < length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [charactersPerSecond, length, resetKey]);

  const finish = useCallback(() => setProgress({ key: resetKey, count: length }), [length, resetKey]);

  return {
    visibleText: characters.slice(0, count).join(""),
    hiddenText: characters.slice(count).join(""),
    complete: count >= length,
    finish,
  };
}
