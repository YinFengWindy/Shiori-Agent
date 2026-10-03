import { useEffect, useState } from "react";
import { copyTextToClipboard } from "./clipboard";
import { errorMessage } from "@yinfengwindy/shiori-sdk";
import { mascotFeedback as feedback } from "./mascot/mascotFeedback";

/** How long a copy button shows its 「已复制」 confirmation. */
export const copiedResetMs = 1600;

/**
 * Copy-button state: `copy` writes the text to the clipboard and flips
 * `copied` on for `copiedResetMs`; a failure is reported as feedback.
 */
export function useCopyText() {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return undefined;
    const timer = window.setTimeout(() => setCopied(false), copiedResetMs);
    return () => window.clearTimeout(timer);
  }, [copied]);
  async function copy(text: string) {
    try {
      await copyTextToClipboard(text);
      setCopied(true);
    } catch (error) {
      feedback.error(`复制失败：${errorMessage(error)}`);
    }
  }
  return { copied, copy };
}
