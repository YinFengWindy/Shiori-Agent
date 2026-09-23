import { useContext, useEffect, useRef } from "react";
import { SoundContext } from "./SoundProvider";

/** The site sound API (`playSfx`, toggle, preview); needs `<SoundProvider>` above. */
export function useSound() {
  const api = useContext(SoundContext);
  if (!api) throw new Error("useSound must be used inside <SoundProvider>");
  return api;
}

/**
 * Play the "advance" blip whenever the ADV dialogue moves to a new line
 * (click, keyboard, auto mode or a chosen topic) — not for the first line.
 */
export function useLineAdvanceSfx(lineKey: number) {
  const { playSfx } = useSound();
  const previousRef = useRef(lineKey);
  useEffect(() => {
    if (lineKey === previousRef.current) return;
    previousRef.current = lineKey;
    playSfx("advance");
  }, [lineKey, playSfx]);
}
