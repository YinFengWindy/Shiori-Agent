import { useState } from "react";
import { cx } from "@shiori/plugin-sdk";
import { PhoneMessageMedia } from "./PhoneMessageMedia";
import type { PhoneQuoteItem } from "./phoneChatPresentation";

// Quoted pictures show as thumbnails; a click enlarges one like the message's own.
const quoteImageBounds = { width: 64, height: 64 };

/**
 * The message a bubble quotes, above it: who is quoted, their text and
 * their pictures. A long text starts clamped; clicking it expands or
 * collapses it.
 */
export function PhoneMessageQuote({ quote, onOpenImage }: {
  quote: PhoneQuoteItem;
  onOpenImage: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const textClass = "m-0 whitespace-pre-wrap break-words text-caption text-ink-secondary";
  return (
    <div className="grid min-w-0 max-w-full gap-1 border-l-2 border-line-accent pl-2.5" data-testid="phone-message-quote">
      {quote.label ? <span className="truncate text-caption font-medium text-ink-muted">{quote.label}</span> : null}
      {quote.content && quote.collapsible ? (
        <button type="button" aria-expanded={expanded} aria-label={expanded ? "收起引用" : "展开引用"}
          className={cx(textClass, "cursor-pointer border-0 bg-transparent p-0 text-left", !expanded && "line-clamp-2")}
          onClick={() => setExpanded((open) => !open)}>
          {quote.content}
        </button>
      ) : quote.content ? <span className={cx(textClass, "block")}>{quote.content}</span> : null}
      {quote.media.length ? (
        <div className="flex flex-wrap gap-1">
          <PhoneMessageMedia media={quote.media} bounds={quoteImageBounds} onOpenImage={onOpenImage} />
        </div>
      ) : null}
    </div>
  );
}
