import type { AriaAttributes } from "react";
import { Select as SelectPrimitive } from "@base-ui/react/select";
import { CaretDown, Check } from "@phosphor-icons/react";
import { cx, inputClass } from "../styles";
import { menuItemClass, menuItemSelectedClass, menuPanelClass } from "./Menu";

/** One selectable business value, including the empty string for default choices. */
export interface SelectOption {
  value: string;
  label: string;
  /** Shorter text for the closed trigger when the list label carries extra annotation. */
  triggerLabel?: string;
  disabled?: boolean;
}

/** Controlled single-select field with an explicit accessible name. */
export interface SelectProps extends AriaAttributes {
  "aria-label": string;
  value: string;
  options: readonly SelectOption[];
  onValueChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
  name?: string;
  className?: string;
}

/** Shared form picker; Base UI owns keyboard, focus, dismissal and portal positioning. */
export function Select({ value, options, onValueChange, disabled, id, name, className, ...aria }: SelectProps) {
  return (
    <SelectPrimitive.Root
      value={value}
      // The trigger renders the item label; the list below always renders the full option label.
      items={options.map((option) => ({ value: option.value, label: option.triggerLabel ?? option.label }))}
      onValueChange={(next) => {
        // Null represents no library selection; empty strings are valid business values.
        if (next !== null && next !== value) onValueChange(next);
      }}
      disabled={disabled}
      id={id}
      name={name}
      modal={false}
    >
      <SelectPrimitive.Trigger
        {...aria}
        className={cx(
          className ?? inputClass,
          "flex min-w-0 items-center justify-between gap-2 text-left transition disabled:cursor-default disabled:opacity-50",
        )}
      >
        <SelectPrimitive.Value className="min-h-[1lh] min-w-0 truncate" />
        <SelectPrimitive.Icon className="flex shrink-0 text-ink-muted">
          <CaretDown className="h-3.5 w-3.5" aria-hidden="true" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Positioner
          align="start"
          alignItemWithTrigger={false}
          sideOffset={4}
          collisionPadding={8}
          className="z-[100] w-[var(--anchor-width)] max-w-[var(--available-width)]"
        >
          <SelectPrimitive.Popup
            className={cx(menuPanelClass, "motion-popup max-h-[var(--available-height)] overflow-hidden")}
            // Portal items belong to this control, including inside an outside-dismissed panel.
            onPointerDown={(event) => event.stopPropagation()}
          >
            <SelectPrimitive.List className="max-h-[min(20rem,calc(var(--available-height)-0.875rem))] overflow-y-auto overscroll-contain">
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                  className={(state) => cx(
                    menuItemClass,
                    "cursor-default data-[highlighted]:bg-surface-hover data-[highlighted]:text-ink data-[disabled]:pointer-events-none data-[disabled]:opacity-45",
                    state.selected && menuItemSelectedClass,
                  )}
                >
                  <SelectPrimitive.ItemText className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">{option.label}</SelectPrimitive.ItemText>
                  <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                    <SelectPrimitive.ItemIndicator><Check className="h-3.5 w-3.5" aria-hidden="true" /></SelectPrimitive.ItemIndicator>
                  </span>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.List>
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
