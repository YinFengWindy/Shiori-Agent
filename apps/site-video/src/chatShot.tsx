import { useEffect, useRef, useState } from "react";
import { cancelRender, continueRender, delayRender, useCurrentFrame } from "remotion";
import chatShot from "../../../assets/readme/chat.png";
import { progress, SCREEN_HEIGHT, SCREEN_WIDTH, ShotRegion, type Rect } from "./screen";

/** The chat screenshot (assets/readme/chat.png) the chat clips are built on. */
export const CHAT_SHOT = chatShot;

/**
 * The message list of chat.png: the pane between the header and the
 * composer, inside the scrollbar. Its one-pixel frame just outside is bare
 * pane background, which `EmptyChatPane` fills the inside from.
 */
const MESSAGE_PANE: Rect = { x: 276, y: 93, w: 815, h: 679 };

/**
 * One message on chat.png, in screenshot pixels: the bubble (radius
 * `BUBBLE_RADIUS`, cut out without its shadow, which `ChatMessages` draws
 * again), plus 吟风's avatar centre and name label on her replies.
 */
interface ChatMessage {
  readonly bubble: Rect;
  readonly reply?: { readonly avatar: { readonly x: number; readonly y: number }; readonly name: Rect };
}

const BUBBLE_RADIUS = 16;
const AVATAR_RADIUS = 17;

/** 吟风's avatar and name above a reply bubble starting at `top`. */
function replyHeader(top: number) {
  return { avatar: { x: 313, y: top - 1 }, name: { x: 339, y: top - 22, w: 30, h: 18 } };
}

/** The six messages on chat.png, top to bottom: user, 吟风, user, 吟风, user, 吟风. */
export const CHAT_MESSAGES: readonly ChatMessage[] = [
  { bubble: { x: 688, y: 98, w: 377, h: 44 } },
  { bubble: { x: 341, y: 199, w: 630, h: 68 }, reply: replyHeader(199) },
  { bubble: { x: 730, y: 309, w: 335, h: 43 } },
  { bubble: { x: 341, y: 409, w: 630, h: 101 }, reply: replyHeader(409) },
  { bubble: { x: 786, y: 551, w: 279, h: 44 } },
  { bubble: { x: 341, y: 652, w: 589, h: 45 }, reply: replyHeader(652) },
];

/** How far a message rises as it fades in, in screenshot pixels. */
const MESSAGE_RISE = 14;
/** Frames a message takes to fade in. */
const MESSAGE_IN = 14;
/** The bubbles' shadow on the screenshot, redrawn under each cut-out bubble. */
const BUBBLE_SHADOW = "0 1px 3px rgba(60, 40, 55, 0.08), 0 6px 18px rgba(95, 26, 58, 0.07)";

/**
 * The message pane with every message taken out: each pixel blended from
 * the pane's frame around it (a Coons patch over the four edges), so the
 * fill meets the real pane seamlessly and follows its blue-to-pink wash.
 * Drawn once from the screenshot's pixels; the screenshot is not changed.
 */
function EmptyChatPane() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender("filling the empty chat pane"));

  useEffect(() => {
    const image = new Image();
    image.src = CHAT_SHOT;
    image
      .decode()
      .then(() => {
        const target = canvas.current;
        if (!target) throw new Error("chat pane canvas is missing");
        const source = document.createElement("canvas");
        source.width = SCREEN_WIDTH;
        source.height = SCREEN_HEIGHT;
        const sourceContext = source.getContext("2d", { willReadFrequently: true });
        const context = target.getContext("2d");
        if (!sourceContext || !context) throw new Error("no 2D canvas context");
        sourceContext.drawImage(image, 0, 0);
        const { x, y, w, h } = MESSAGE_PANE;
        // The frame: one row above and below, one column left and right (corners included).
        const top = sourceContext.getImageData(x - 1, y - 1, w + 2, 1).data;
        const bottom = sourceContext.getImageData(x - 1, y + h, w + 2, 1).data;
        const left = sourceContext.getImageData(x - 1, y - 1, 1, h + 2).data;
        const right = sourceContext.getImageData(x + w, y - 1, 1, h + 2).data;
        const out = context.createImageData(w, h);
        for (let row = 0; row < h; row++) {
          const v = (row + 1) / (h + 1);
          for (let column = 0; column < w; column++) {
            const u = (column + 1) / (w + 1);
            const at = (row * w + column) * 4;
            for (let channel = 0; channel < 3; channel++) {
              const t = top[(column + 1) * 4 + channel] ?? 0;
              const b = bottom[(column + 1) * 4 + channel] ?? 0;
              const l = left[(row + 1) * 4 + channel] ?? 0;
              const r = right[(row + 1) * 4 + channel] ?? 0;
              const c00 = top[channel] ?? 0;
              const c10 = top[(w + 1) * 4 + channel] ?? 0;
              const c01 = bottom[channel] ?? 0;
              const c11 = bottom[(w + 1) * 4 + channel] ?? 0;
              out.data[at + channel] =
                (1 - v) * t + v * b + (1 - u) * l + u * r -
                ((1 - u) * (1 - v) * c00 + u * (1 - v) * c10 + (1 - u) * v * c01 + u * v * c11);
            }
            out.data[at + 3] = 255;
          }
        }
        context.putImageData(out, 0, 0);
        continueRender(handle);
      })
      .catch((error: unknown) => cancelRender(error));
  }, [handle]);

  return (
    <canvas
      ref={canvas}
      width={MESSAGE_PANE.w}
      height={MESSAGE_PANE.h}
      style={{ position: "absolute", left: MESSAGE_PANE.x, top: MESSAGE_PANE.y }}
    />
  );
}

/**
 * The chat screenshot's message pane, emptied, with each message cut back
 * in from the screenshot at its frame in `appearAt` (one entry per message,
 * in frames; a negative frame shows it from the start), fading in, rising.
 */
export function ChatMessages({ appearAt }: { appearAt: readonly number[] }) {
  const frame = useCurrentFrame();
  return (
    <>
      <EmptyChatPane />
      {CHAT_MESSAGES.map((message, index) => {
        const at = appearAt[index];
        if (at === undefined) throw new Error(`no appearance frame for chat message ${index}`);
        const shown = at < 0 ? 1 : progress(frame, at, MESSAGE_IN);
        const motion = { opacity: shown, transform: `translateY(${(1 - shown) * MESSAGE_RISE}px)` };
        const { reply } = message;
        return (
          <div key={index} style={{ position: "absolute", inset: 0, ...motion }}>
            {reply && (
              <>
                <ShotRegion
                  src={CHAT_SHOT}
                  rect={{
                    x: reply.avatar.x - AVATAR_RADIUS,
                    y: reply.avatar.y - AVATAR_RADIUS,
                    w: AVATAR_RADIUS * 2,
                    h: AVATAR_RADIUS * 2,
                  }}
                  style={{ borderRadius: 9999 }}
                />
                <ShotRegion src={CHAT_SHOT} rect={reply.name} />
              </>
            )}
            <ShotRegion src={CHAT_SHOT} rect={message.bubble} style={{ borderRadius: BUBBLE_RADIUS, boxShadow: BUBBLE_SHADOW }} />
          </div>
        );
      })}
    </>
  );
}
