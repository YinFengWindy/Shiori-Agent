import { useEffect, useRef, type ReactNode } from "react";
import { CaretLeftIcon } from "@phosphor-icons/react";
import { compactIconButtonClass } from "../shared/styles";

/**
 * A phone screen's glass header: a back button, the screen's title and an
 * optional trailing action. With `focusBack` the back button takes focus
 * when it mounts or `focusBack` turns true (a screen just opened or came back on top).
 */
export function PhoneScreenHeader({ title, backLabel, onBack, action, focusBack = false }: {
  title: string;
  /** Accessible name of the back button (where it goes). */
  backLabel: string;
  onBack: () => void;
  /** Sits at the header's right end (e.g. the chat page's info button). */
  action?: ReactNode;
  focusBack?: boolean;
}) {
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (focusBack) backRef.current?.focus();
  }, [focusBack]);
  return (
    <header className="surface-glass flex min-w-0 items-center gap-1 px-2 py-1.5">
      <button ref={backRef} type="button" aria-label={backLabel} data-testid="phone-back" onClick={onBack} className={compactIconButtonClass}>
        <CaretLeftIcon className="h-4 w-4" aria-hidden="true" />
      </button>
      <h3 className="m-0 min-w-0 flex-1 truncate text-body font-semibold text-ink">{title}</h3>
      {action}
    </header>
  );
}
