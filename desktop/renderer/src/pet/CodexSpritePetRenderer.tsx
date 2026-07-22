import { useEffect, useState } from "react";
import { spriteCell, spriteAnimations, spriteFrameDuration, spriteFramePosition, type SpriteState } from "./spriteContract";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
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
      className="pet-drag-region"
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(state, activeFrame),
        backgroundRepeat: "no-repeat",
        cursor: "grab",
      }}
    />
  );
}
