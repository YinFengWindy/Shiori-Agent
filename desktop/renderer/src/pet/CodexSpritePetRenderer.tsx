import { useEffect, useRef, useState } from "react";
import { spriteCell, spriteAnimations, spriteFramePosition, type SpriteState } from "./spriteContract";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const drag = useRef<{ pointerId: number; x: number; y: number } | null>(null);
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
        if (event.button !== 0) return;
        drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const activeDrag = drag.current;
        if (activeDrag?.pointerId === event.pointerId) {
          window.miraDesktop.movePet(event.screenX - activeDrag.x, event.screenY - activeDrag.y);
        }
      }}
      onPointerUp={(event) => {
        if (drag.current?.pointerId !== event.pointerId) return;
        drag.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
      }}
      onPointerCancel={() => {
        drag.current = null;
      }}
      onDoubleClick={() => window.miraDesktop.openPetRole()}
      onContextMenu={(event) => {
        event.preventDefault();
        window.miraDesktop.openPetMenu();
      }}
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(state, frame),
        backgroundRepeat: "no-repeat",
        touchAction: "none",
        cursor: "grab",
      }}
    />
  );
}
