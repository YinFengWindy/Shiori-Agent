import type React from "react";
import { cx } from "@shiori/plugin-sdk";

/**
 * The drag strip along a left sidebar's trailing edge.
 *
 * Extracted because this markup had been copied into every sidebar that sits
 * in the shell's resizable track — `RoleSidebar`, `SettingsSidebar`,
 * `RoleWorkspaceSidebar`, and, once a plugin could own that track (#226), the
 * two novelai ones as well. Five copies of the same three attributes is how a
 * sidebar quietly ends up with a different accessible name or a handle that
 * stays grabbable while collapsed.
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
