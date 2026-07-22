import { useEffect, useState } from "react";
import { spriteCell, spriteAnimations, spriteFrameDuration, spriteFramePosition, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const { interactionState, pointerHandlers } = useCodexPetInteraction(window.miraDesktop);
  const activeState = interactionState ?? state;
  const animation = spriteAnimations[activeState];
  const activeFrame = frame % animation.frames;

  useEffect(() => {
    setFrame(0);
  }, [activeState]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFrame((current) => (current + 1) % animation.frames);
    }, spriteFrameDuration(activeState, activeFrame));
    return () => window.clearTimeout(timer);
  }, [activeFrame, animation]);

  return (
    <div
      aria-label="桌宠"
      {...pointerHandlers}
      onDoubleClick={() => window.miraDesktop.openPetRole()}
      onContextMenu={(event) => {
        event.preventDefault();
        window.miraDesktop.openPetMenu();
      }}
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(activeState, activeFrame),
        backgroundRepeat: "no-repeat",
        touchAction: "none",
        cursor: "grab",
      }}
    />
  );
}
