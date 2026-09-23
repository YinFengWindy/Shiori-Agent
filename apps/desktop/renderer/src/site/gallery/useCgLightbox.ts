import { useCallback, useEffect, useRef, useState } from "react";
import { useSound } from "../sound/useSound";
import { closeLightbox, createLightbox, lightboxCounter, openLightbox, stepLightbox } from "./lightboxModel";

/**
 * CG gallery lightbox controller: wraps the pure `lightboxModel` state, plays
 * the open/close/advance sounds, and hands focus back to the thumbnail of
 * the image that was showing when the lightbox closes (which may differ from
 * the one that opened it after ←/→). Thumbnails register via `thumbRef(i)`.
 */
export function useCgLightbox(count: number) {
  const [state, setState] = useState(() => createLightbox(count));
  const thumbsRef = useRef<Array<HTMLButtonElement | null>>([]);
  const wasOpenRef = useRef(false);
  const { playSfx } = useSound();

  const open = useCallback(
    (index: number) => {
      playSfx("open");
      setState((prev) => openLightbox(prev, index));
    },
    [playSfx],
  );
  const close = useCallback(() => {
    playSfx("close");
    setState(closeLightbox);
  }, [playSfx]);
  const step = useCallback(
    (delta: number) => {
      playSfx("advance");
      setState((prev) => stepLightbox(prev, delta));
    },
    [playSfx],
  );
  const showNext = useCallback(() => step(1), [step]);
  const showPrevious = useCallback(() => step(-1), [step]);

  // Runs after the dialog's own focus cleanup (`useDialogFocus` restores the
  // opener), so the thumbnail of the last-shown image wins.
  useEffect(() => {
    if (wasOpenRef.current && !state.open) thumbsRef.current[state.index]?.focus();
    wasOpenRef.current = state.open;
  }, [state.open, state.index]);

  const thumbRef = useCallback(
    (index: number) => (element: HTMLButtonElement | null) => {
      thumbsRef.current[index] = element;
    },
    [],
  );

  return {
    open: state.open,
    index: state.index,
    counter: lightboxCounter(state),
    openAt: open,
    close,
    showNext,
    showPrevious,
    thumbRef,
  };
}
