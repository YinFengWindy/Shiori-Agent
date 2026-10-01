import { useState } from "react";
import { cx } from "@shiori/sdk";
import { replyQuoteButtonClass, replyQuoteFrameClass, replyQuoteSenderClass, replyQuoteTextClass } from "../shared/styles";
import { PhoneMessageMedia } from "./PhoneMessageMedia";
import { phoneQuoteCollapsedLines, type PhoneQuoteItem } from "./phoneChatPresentation";

// Quoted pictures show as thumbnails; a click enlarges one like the message's own.
const quoteImageBounds = { width: 64, height: 64 };

const quoteTextClass = cx(replyQuoteTextClass, "m-0 block whitespace-pre-wrap break-words text-ink-secondary");

// Tailwind 3 only has fixed line-clamp classes, so the clamp is styled from the line count the presentation decides by.
const collapsedStyle = {
  display: "-webkit-box",
  overflow: "hidden",
  WebkitBoxOrient: "vertical",
  WebkitLineClamp: phoneQuoteCollapsedLines,
} as const;

/**
 * The message a bubble quotes, above it, framed like the desktop's reply
 * quotes: who is quoted, their text and their pictures. A long text starts
 * clamped; clicking it expands or collapses it.
 */
export function PhoneMessageQuote({ quote, onOpenImage }: {
  quote: PhoneQuoteItem;
  onOpenImage: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={cx(replyQuoteFrameClass, "grid min-w-0 max-w-full gap-1")} data-testid="phone-message-quote">
      {quote.label ? <span className={replyQuoteSenderClass}>{quote.label}</span> : null}
      {quote.content && quote.collapsible ? (
        <button type="button" aria-expanded={expanded} className={cx(replyQuoteButtonClass, quoteTextClass, "cursor-pointer")}
          style={expanded ? undefined : collapsedStyle} onClick={() => setExpanded((open) => !open)}>
          {quote.content}
        </button>
      ) : quote.content ? <span className={quoteTextClass}>{quote.content}</span> : null}
      {quote.media.length ? (
        <div className="flex flex-wrap gap-1">
          <PhoneMessageMedia media={quote.media} bounds={quoteImageBounds} onOpenImage={onOpenImage} />
        </div>
      ) : null}
    </div>
  );
}
