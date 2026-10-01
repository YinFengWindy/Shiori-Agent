import type React from "react";
import { cx } from "../styles";

/**
 * Starts resizing the shell's sidebar track. A collapsed sidebar keeps a
 * zero-width handle so it cannot intercept the shell's expand affordance.
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
