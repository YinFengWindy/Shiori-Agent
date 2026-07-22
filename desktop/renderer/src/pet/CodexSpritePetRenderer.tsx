import { useEffect, useState } from "react";
import { spriteCell, spriteAnimations, spriteFramePosition, type SpriteState } from "./spriteContract";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
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
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(state, frame),
        backgroundRepeat: "no-repeat",
      }}
    />
  );
}
