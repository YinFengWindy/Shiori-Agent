import { useEffect, useRef, useState } from "react";

/** Resize the same role sidebar used by the desktop while cleaning up pointer listeners. */
export function useDemoSidebar() {
  const [width, setWidth] = useState(208);
  const cleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => cleanup.current?.(), []);
  return {
    width,
    beginResize(event: React.PointerEvent<HTMLDivElement>) {
      cleanup.current?.();
      const startX = event.clientX;
      const startWidth = width;
      const move = (next: PointerEvent) => setWidth(Math.max(160, Math.min(320, startWidth + next.clientX - startX)));
      const end = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", end); document.removeEventListener("pointercancel", end); cleanup.current = null; };
      cleanup.current = end;
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", end);
      document.addEventListener("pointercancel", end);
    },
  };
}
