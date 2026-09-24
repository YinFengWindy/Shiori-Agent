import type { RefObject } from "react";
import { CrossfadeLayers } from "../shared/CrossfadeLayers";
import { cx } from "../shared/styles";

type ChatSurfaceBackdropProps = {
  url: string;
  /** The role the background belongs to: a role switch swaps it outright (the view transition animates it). */
  resetKey: string;
  /** The layer `useChatBackdropMotion` shifts for the pointer parallax. */
  parallaxRef: RefObject<HTMLDivElement | null>;
  /** Ambient motion on: the portrait breathes (and the parallax layer is promoted). */
  motion: boolean;
  /** Window hidden or blurred: the breathing holds where it is. */
  paused: boolean;
};

/**
 * The role's chat background behind the conversation, with the left-to-right
 * wash that keeps messages readable. A background change crossfades. The
 * portrait sits on a layer that bleeds 12px past the frame so the parallax
 * never shows an edge; the wash stays fixed.
 */
export function ChatSurfaceBackdrop({ url, resetKey, parallaxRef, motion, paused }: ChatSurfaceBackdropProps) {
  return (
    <div
      className="conversation-illustration pointer-events-none absolute inset-0 z-0 overflow-hidden"
      aria-hidden="true"
      data-chat-backdrop=""
    >
      <div ref={parallaxRef} className={cx("chat-backdrop-parallax absolute -inset-3", motion && "chat-backdrop-parallax-live")}>
        <div className={cx("absolute inset-0", motion && "chat-backdrop-breathe")} data-paused={paused || undefined}>
          <CrossfadeLayers
            value={url}
            resetKey={resetKey}
            render={(layerUrl) => (
              <div
                className="conversation-illustration-image absolute inset-0 bg-cover bg-center bg-no-repeat opacity-[0.96]"
                style={{ backgroundImage: `url("${layerUrl}")` }}
              />
            )}
          />
        </div>
      </div>
      <div className="conversation-illustration-fade absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.78)_0%,rgba(255,255,255,0.64)_24%,rgba(255,255,255,0.4)_48%,rgba(255,255,255,0.14)_72%,rgba(255,255,255,0.03)_100%)]" />
    </div>
  );
}
