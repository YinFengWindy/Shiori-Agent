import { Fragment, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { cx } from "../styles";
import { menuItemClass, menuPanelClass, menuSeparatorClass } from "./Menu";

/** One row of an `ActionMenu`; a `danger` row is drawn in the destructive tone. */
export type ActionMenuItem = {
  id: string;
  label: string;
  icon?: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  /** Draws a divider above this row, separating it from the rows before. */
  separated?: boolean;
  onSelect: () => void;
};

type ActionMenuProps = {
  /** Accessible name of the trigger button. */
  label: string;
  /** The trigger's visible content (usually a single icon). */
  children: ReactNode;
  triggerClassName?: string;
  items: readonly ActionMenuItem[];
  disabled?: boolean;
  align?: "start" | "center" | "end";
  "data-testid"?: string;
};

/**
 * A small overflow menu (「…」) for secondary actions. Base UI owns keyboard
 * navigation, focus return, outside dismissal and positioning; the look comes
 * from the shared menu vocabulary so it reads as one family with the other menus.
 */
export function ActionMenu({ label, children, triggerClassName, items, disabled, align = "end", ...rest }: ActionMenuProps) {
  return (
    <Menu.Root modal={false}>
      <Menu.Trigger className={triggerClassName} aria-label={label} disabled={disabled} data-testid={rest["data-testid"]}>
        {children}
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align={align} sideOffset={6} collisionPadding={8} className="z-[100]">
          <Menu.Popup className={cx(menuPanelClass, "motion-popup min-w-[148px] outline-none")}>
            {items.map((item) => (
              <Fragment key={item.id}>
                {item.separated ? <div className={menuSeparatorClass} role="separator" /> : null}
                <Menu.Item
                  className={cx(
                    menuItemClass,
                    "cursor-default data-[highlighted]:bg-surface-hover data-[highlighted]:text-ink",
                    item.danger && "text-danger-text data-[highlighted]:bg-danger-soft data-[highlighted]:text-danger-text",
                  )}
                  disabled={item.disabled}
                  onClick={item.onSelect}
                >
                  {item.icon ? <span className="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">{item.icon}</span> : null}
                  {item.label}
                </Menu.Item>
              </Fragment>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
