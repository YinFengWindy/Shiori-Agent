import { useEffect, useEffectEvent, useLayoutEffect, useState } from "react";
import type React from "react";
import {
  getChatComposerPopoverPosition,
  type ChatComposerPopoverAlign,
  type ChatComposerPopoverPosition,
} from "./chatComposerPopoverLayout";

type UseChatComposerPopoverOptions = {
  open: boolean;
  onClose: () => void;
  /** The button that toggles the popover; Escape hands focus back to it. */
  triggerRef: React.RefObject<HTMLElement | null>;
  /** The portalled panel; pointer-downs inside it (or on the trigger) do not close it. */
  popoverRef: React.RefObject<HTMLElement | null>;
  /** Rendered panel width, needed to clamp the panel into the window before it renders. */
  width: number;
  align?: ChatComposerPopoverAlign;
  gap?: number;
};

/**
 * Shared behaviour of the composer's popovers (model menu, emoji panel): they
 * render into a body portal with `position: fixed`, because the composer card
 * clips its content (`overflow: hidden`, and `backdrop-filter` makes it the
 * containing block even for fixed descendants). This hook keeps the panel
 * placed above its trigger while the window resizes or anything scrolls, and
 * closes it on an outside pointer-down or Escape (returning focus to the
 * trigger). Returns the position, or `null` while closed / not yet measured.
 */
export function useChatComposerPopover({
  open,
  onClose,
  triggerRef,
  popoverRef,
  width,
  align = "start",
  gap = 4,
}: UseChatComposerPopoverOptions) {
  const [position, setPosition] = useState<ChatComposerPopoverPosition | null>(null);
  const close = useEffectEvent(onClose);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || popoverRef.current?.contains(target)) return;
      close();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      close();
      triggerRef.current?.focus();
    };
    window.addEventListener("pointerdown", closeOnOutsidePointer, true);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnOutsidePointer, true);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, popoverRef, triggerRef]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    const updatePosition = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosition(getChatComposerPopoverPosition(rect, { width: window.innerWidth, height: window.innerHeight }, width, { align, gap }));
    };
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [align, gap, open, triggerRef, width]);

  return open ? position : null;
}
