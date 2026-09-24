import { brandMotifPaths } from "../shared/ui/icons";

/**
 * The 「正在输入…」 mark: three brand sparkles (sky, pink, lavender) hopping
 * and twinkling in turn. Decorative; the caller carries the status text.
 * Styles: `.chat-typing-sparkles` in styles.css (still under reduced motion).
 */
export function ChatTypingSparkles() {
  return (
    <span className="chat-typing-sparkles" aria-hidden="true" data-testid="chat-typing-sparkles">
      {[0, 1, 2].map((index) => (
        <span key={index}>
          {/* Cropped to the sparkle's own 16×16 so three fit a caption line. */}
          <svg viewBox="4 4 16 16">
            <path d={brandMotifPaths.sparkle} fill="currentColor" />
          </svg>
        </span>
      ))}
    </span>
  );
}
