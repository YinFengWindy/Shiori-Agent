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

/**
 * Menu-style button sounds: a soft blip on hover and a chime on click, as
 * the title menu plays them. Spread `hover` on `onPointerEnter` and call
 * `click` from the button's click handler.
 */
export function useButtonSfx() {
  const { playSfx } = useSound();
  return {
    hover: () => playSfx("hover"),
    click: () => playSfx("click"),
  };
}
