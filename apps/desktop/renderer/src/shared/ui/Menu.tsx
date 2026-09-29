import React from "react";
import { cx, menuPanelClass } from "@shiori/plugin-sdk";
import { menuItemClass, menuItemSelectedClass } from "@shiori/plugin-sdk/host-internal";

/*
 * The menu vocabulary (panel, row, selected row, separator) is owned by
 * `@shiori/plugin-sdk` (#440) and re-exported here; the hand-rolled menu
 * pieces below stay host-only.
 */
export { menuPanelClass, menuSeparatorClass } from "@shiori/plugin-sdk";
export { menuItemClass, menuItemSelectedClass } from "@shiori/plugin-sdk/host-internal";

/** Non-interactive group caption. */
export const menuLabelClass = "px-2.5 py-1 text-[11px] text-ink-muted";

type MenuPanelProps = React.HTMLAttributes<HTMLDivElement> & {
  ref?: React.Ref<HTMLDivElement>;
};

/** Renders a floating menu surface; pass positioning via className/style. */
export function MenuPanel({ className, ...rest }: MenuPanelProps) {
  return <div className={cx(menuPanelClass, className)} {...rest} />;
}

type MenuItemProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  selected?: boolean;
};

/** Keys `moveMenuFocus` handles. */
const menuNavigationKeys = new Set(["ArrowDown", "ArrowUp", "Home", "End"]);

/**
 * Roving keyboard focus for a hand-rolled menu panel: ArrowDown / ArrowUp move
 * between the rows matched by `itemSelector` (wrapping), Home / End jump to
 * the ends. Call from the panel's onKeyDown; other keys pass through.
 */
export function moveMenuFocus(event: React.KeyboardEvent<HTMLElement>, itemSelector: string): void {
  if (!menuNavigationKeys.has(event.key)) return;
  const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(itemSelector));
  if (!items.length) return;
  event.preventDefault();
  const index = items.indexOf(document.activeElement as HTMLElement);
  const next = event.key === "Home" ? 0
    : event.key === "End" ? items.length - 1
      : event.key === "ArrowDown" ? (index + 1) % items.length
        : (index - 1 + items.length) % items.length;
  items[next]?.focus();
}

/** Renders one menu row; `selected` switches to the accent treatment. */
export function MenuItem({ className, selected, type, ...rest }: MenuItemProps) {
  return (
    <button
      className={cx(menuItemClass, selected && menuItemSelectedClass, className)}
      type={type ?? "button"}
      aria-current={selected ? "true" : undefined}
      {...rest}
    />
  );
}
