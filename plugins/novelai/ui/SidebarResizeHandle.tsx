import type React from "react";
import { cx } from "@shiori/plugin-sdk";

/**
 * The drag strip along the novelai sidebar's trailing edge. The host's
 * resizable track hands the sidebar `onBeginResize`; this strip starts it.
 * novelai owns this copy (#509): the host keeps its own for its sidebars,
 * with the same accessible name and collapse behaviour.
 *
 * Collapsing to zero width rather than hiding the element is deliberate: the
 * shell renders its own expand affordance over `<main>`'s edge while the
 * sidebar is collapsed, so a still-grabbable strip here would sit underneath
 * it and win the pointer.
 */
export function SidebarResizeHandle({
  collapsed,
  onBeginResize,
}: {
  collapsed: boolean;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className={cx(
        "sidebar-resize-handle absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent",
        collapsed ? "w-0" : "w-2",
      )}
      role="separator"
      aria-label="调整侧边栏宽度"
      aria-orientation="vertical"
      onPointerDown={onBeginResize}
    />
  );
}
