import { DeviceMobileIcon } from "@phosphor-icons/react";
import { cx } from "@shiori/plugin-sdk";
import { compactIconButtonClass } from "../shared/styles";
import { Tooltip } from "../shared/ui/Tooltip";

/** The chat header's button that opens and closes the role's phone. */
export function PhoneToggle({ open, onToggle, className }: { open: boolean; onToggle: () => void; className?: string }) {
  const label = open ? "收起手机" : "打开手机";
  return (
    <Tooltip label={label} side="bottom">
      <button
        className={cx(compactIconButtonClass, open && "text-accent-text", className)}
        type="button"
        aria-label={label}
        aria-expanded={open}
        data-testid="phone-toggle"
        onClick={onToggle}
      >
        <DeviceMobileIcon className="h-4 w-4" weight={open ? "fill" : "regular"} aria-hidden="true" />
      </button>
    </Tooltip>
  );
}
