import React from "react";
import { Check, Copy } from "@phosphor-icons/react";
import { copyTextToClipboard } from "../shared/clipboard";
import { errorMessage, feedback } from "../shared/feedback/feedbackStore";
import { compactPressableClass, cx } from "../shared/styles";
import { useHighlightedChatCode } from "./chatCodeHighlight";

/** How long the copy button shows its 「已复制」 confirmation. */
const copiedResetMs = 1600;

type ChatCodeBlockProps = {
  code: string;
  /** Fenced-code language, lower-cased; empty when the fence had none. */
  language: string;
};

/** Renders one fenced code block with a language header, a copy button and lazy syntax highlighting. */
export const ChatCodeBlock = React.memo(function ChatCodeBlock({ code, language }: ChatCodeBlockProps) {
  const highlighted = useHighlightedChatCode(code, language);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    if (!copied) return undefined;
    const timer = window.setTimeout(() => setCopied(false), copiedResetMs);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copyCode(): Promise<void> {
    try {
      await copyTextToClipboard(code);
      setCopied(true);
    } catch (error) {
      feedback.error(`复制失败：${errorMessage(error)}`);
    }
  }

  return (
    <div className="chat-code-block my-2 max-w-full overflow-hidden rounded-md border border-line-soft bg-surface-soft" data-testid="chat-code-block">
      <div className="flex h-8 items-center justify-between gap-2 border-b border-line-soft pl-3 pr-1">
        <span className="truncate font-mono text-caption text-ink-muted">{language || "代码"}</span>
        <button
          className={cx(
            compactPressableClass,
            "inline-flex h-6 flex-none items-center gap-1 rounded-md px-1.5 text-caption text-ink-muted hover:bg-surface-hover hover:text-ink",
          )}
          type="button"
          aria-label={copied ? "已复制代码" : "复制代码"}
          onClick={() => void copyCode()}
        >
          {copied ? <Check className="h-3.5 w-3.5 text-success-text" weight="bold" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
          <span>{copied ? "已复制" : "复制"}</span>
        </button>
      </div>
      <pre className="scrollbar-soft max-w-full overflow-x-auto p-3 font-mono text-[12px] leading-5 text-ink">
        {highlighted === null
          ? <code>{code}</code>
          // highlight.js escapes the code text; the only markup is its own token spans.
          : <code className="hljs" dangerouslySetInnerHTML={{ __html: highlighted }} />}
      </pre>
    </div>
  );
});
