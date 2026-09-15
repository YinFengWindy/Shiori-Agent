/** Watches actual user input so layout and programmatic scroll events cannot cancel following. */
export function listenForChatScrollIntent(container: HTMLDivElement, leaveBottom: () => void) {
  let pointerScrolling = false;
  let previousTop = container.scrollTop;
  let touchY: number | null = null;
  const wheel = (event: WheelEvent) => { if (event.deltaY < 0) leaveBottom(); };
  const touchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? null; };
  const touchMove = (event: TouchEvent) => {
    const nextY = event.touches[0]?.clientY ?? null;
    if (nextY !== null && touchY !== null && nextY > touchY) leaveBottom();
    touchY = nextY;
  };
  const keyDown = (event: KeyboardEvent) => {
    const target = event.target;
    if (target instanceof HTMLElement && (
      target.closest("input, textarea, select, [contenteditable=true]")
      || (!container.contains(target) && target !== document.body && target !== document.documentElement)
    )) return;
    if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) {
      leaveBottom();
    }
  };
  const pointerDown = (event: PointerEvent) => {
    // Native scrollbar input targets the scroll container, unlike message controls.
    pointerScrolling = event.target === container && event.button === 0;
    previousTop = container.scrollTop;
  };
  const pointerUp = () => { pointerScrolling = false; };
  const scroll = () => {
    if (pointerScrolling && container.scrollTop < previousTop) leaveBottom();
    previousTop = container.scrollTop;
  };
  container.addEventListener("wheel", wheel, { passive: true });
  container.addEventListener("touchstart", touchStart, { passive: true });
  container.addEventListener("touchmove", touchMove, { passive: true });
  container.addEventListener("pointerdown", pointerDown, { passive: true });
  container.addEventListener("scroll", scroll, { passive: true });
  window.addEventListener("keydown", keyDown);
  window.addEventListener("pointerup", pointerUp, { passive: true });
  window.addEventListener("pointercancel", pointerUp, { passive: true });
  return () => {
    container.removeEventListener("wheel", wheel);
    container.removeEventListener("touchstart", touchStart);
    container.removeEventListener("touchmove", touchMove);
    container.removeEventListener("pointerdown", pointerDown);
    container.removeEventListener("scroll", scroll);
    window.removeEventListener("keydown", keyDown);
    window.removeEventListener("pointerup", pointerUp);
    window.removeEventListener("pointercancel", pointerUp);
  };
}
