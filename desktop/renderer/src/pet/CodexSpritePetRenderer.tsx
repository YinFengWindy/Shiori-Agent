import { useEffect, useRef, useState } from "react";
import { spriteCell, spriteAnimations, spriteFrameDuration, spriteFramePosition, type SpriteState } from "./spriteContract";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const dragOffset = useRef<{ x: number; y: number } | null>(null);
  const animation = spriteAnimations[state];
  const activeFrame = frame % animation.frames;

  useEffect(() => {
    setFrame(0);
  }, [state]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFrame((current) => (current + 1) % animation.frames);
    }, spriteFrameDuration(state, activeFrame));
    return () => window.clearTimeout(timer);
  }, [activeFrame, animation]);

  return (
    <div
      aria-label="桌宠"
      onPointerDown={(event) => {
        dragOffset.current = { x: event.clientX, y: event.clientY };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const offset = dragOffset.current;
        if (offset) window.miraDesktop.movePet(event.screenX - offset.x, event.screenY - offset.y);
      }}
      onPointerUp={(event) => {
        dragOffset.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
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
        backgroundPosition: spriteFramePosition(state, activeFrame),
        backgroundRepeat: "no-repeat",
        touchAction: "none",
      }}
    />
  );
}
