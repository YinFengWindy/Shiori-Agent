import { useEffect, useState } from "react";

type Highlighter = typeof import("./chatCodeHighlighter");

let highlighterPromise: Promise<Highlighter> | null = null;

/** Loads the highlighter chunk once; later calls share the same promise. */
function loadChatCodeHighlighter(): Promise<Highlighter> {
  highlighterPromise ??= import("./chatCodeHighlighter");
  return highlighterPromise;
}

/**
 * Returns highlighted HTML for one code block, or null until the highlighter
 * chunk has loaded (and for languages it does not know), in which case the
 * caller shows the plain text.
 */
export function useHighlightedChatCode(code: string, language: string): string | null {
  const [highlighter, setHighlighter] = useState<Highlighter | null>(null);
  useEffect(() => {
    if (!language) return undefined;
    let active = true;
    void loadChatCodeHighlighter().then((loaded) => {
      if (active) setHighlighter(() => loaded);
    });
    return () => { active = false; };
  }, [language]);
  return highlighter && language ? highlighter.highlightChatCode(code, language) : null;
}

/** Reads the fenced-code language from react-markdown's `language-xxx` class. */
export function getChatCodeLanguage(className: string | undefined): string {
  const match = /(?:^|\s)language-([\w#+.-]+)/.exec(className ?? "");
  return match ? match[1]!.toLowerCase() : "";
}
