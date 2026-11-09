import React from "react";
import { useEffect, useState } from "react";
import { spriteActionDurationMs, spriteCell, spriteFramePosition, spritePlaybackFrameAt, type SpriteState } from "./spriteContract";

/** Draws only sprite frames; chrome, replies and gestures belong to the shared shell. */
export function CodexSpritePetRenderer({ spritesheetUrl, state, transientState, onTransientFinished, onLoaded, onFailed }: {
  spritesheetUrl: string;
  state: SpriteState;
  transientState: SpriteState | null;
  onTransientFinished: () => void;
  onLoaded: () => void;
  onFailed: () => void;
}) {
  const [frame, setFrame] = useState(0);
  const active = transientState ?? state;
  const playback = spritePlaybackFrameAt(active, frame);
  useEffect(() => { setFrame(0); }, [active]);
  useEffect(() => {
    if (!transientState) return;
    const timer = setTimeout(onTransientFinished, spriteActionDurationMs(transientState));
    return () => clearTimeout(timer);
  }, [transientState, onTransientFinished]);
  useEffect(() => {
    const timer = setTimeout(() => setFrame((value) => value + 1), playback.duration);
    return () => clearTimeout(timer);
  }, [active, frame, playback.duration]);
  return <div style={{ width: spriteCell.width, height: spriteCell.height, backgroundImage: `url(${JSON.stringify(spritesheetUrl)})`, backgroundPosition: spriteFramePosition(playback.state, playback.frame), backgroundRepeat: "no-repeat", pointerEvents: "none" }}>
    <img src={spritesheetUrl} alt="" aria-hidden="true" style={{ display: "none" }} onLoad={onLoaded} onError={onFailed} />
  </div>;
}
