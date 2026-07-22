import { useEffect, useRef, useState } from "react";
import { spriteCell, spriteAnimations, spriteFramePosition, type SpriteState } from "./spriteContract";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const [bubbleVisible, setBubbleVisible] = useState(false);
  const dragOffset = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const animation = spriteAnimations[state];

  useEffect(() => {
    setFrame(0);
    const timer = window.setInterval(() => {
      setFrame((current) => (current + 1) % animation.frames);
    }, animation.duration);
    return () => window.clearInterval(timer);
  }, [animation.duration, animation.frames, state]);

  return (
    <div
      aria-label="桌宠"
      onPointerDown={(event) => {
        dragOffset.current = { x: event.clientX, y: event.clientY };
        dragged.current = false;
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const offset = dragOffset.current;
        if (offset) {
          dragged.current = dragged.current || Math.abs(event.clientX - offset.x) > 2 || Math.abs(event.clientY - offset.y) > 2;
          window.miraDesktop.movePet(event.screenX - offset.x, event.screenY - offset.y);
        }
      }}
      onPointerUp={(event) => {
        dragOffset.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onClick={() => {
        if (!dragged.current) setBubbleVisible(true);
      }}
      onDoubleClick={() => window.miraDesktop.openPetRole()}
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(state, frame),
        backgroundRepeat: "no-repeat",
        touchAction: "none",
        position: "relative",
      }}
    >
      {bubbleVisible ? (
        <button
          aria-label="关闭互动气泡"
          className="absolute bottom-full left-1/2 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md bg-white px-2 py-1 text-xs text-[#32363C] shadow"
          type="button"
          onClick={() => setBubbleVisible(false)}
        >
          在这里
        </button>
      ) : null}
    </div>
  );
}
