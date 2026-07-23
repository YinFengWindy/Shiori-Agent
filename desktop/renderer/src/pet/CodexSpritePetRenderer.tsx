import { useEffect, useState } from "react";
import { spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";
import { useCodexPetInteraction } from "./useCodexPetInteraction";

type CodexSpritePetRendererProps = {
  spritesheetUrl: string;
  state: SpriteState;
};

/** Renders the fixed Codex sprite atlas with its documented state rows and cadence. */
export function CodexSpritePetRenderer({ spritesheetUrl, state }: CodexSpritePetRendererProps) {
  const [frame, setFrame] = useState(0);
  const { interactionState, isDragging, pointerHandlers } = useCodexPetInteraction(
    typeof window === "undefined" ? null : window.miraDesktop,
  );
  const activeState = interactionState ?? state;
  const activePlaybackFrame = spritePlaybackFrameAt(activeState, frame);

  useEffect(() => {
    setFrame(0);
  }, [activeState]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFrame((current) => current + 1);
    }, activePlaybackFrame.duration);
    return () => window.clearTimeout(timer);
  }, [activePlaybackFrame.duration, activeState, frame]);

  return (
    <div
      aria-label="桌宠"
      className={isDragging ? "pet-drag-region pet-dragging" : "pet-drag-region"}
      {...pointerHandlers}
      onLostPointerCapture={pointerHandlers.onPointerCancel}
      onContextMenu={(event) => {
        event.preventDefault();
        window.miraDesktop.openPetMenu();
      }}
      style={{
        width: spriteCell.width,
        height: spriteCell.height,
        backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`,
        backgroundPosition: spriteFramePosition(activePlaybackFrame.state, activePlaybackFrame.frame),
        backgroundRepeat: "no-repeat",
        touchAction: "none",
      }}
    />
  );
}
