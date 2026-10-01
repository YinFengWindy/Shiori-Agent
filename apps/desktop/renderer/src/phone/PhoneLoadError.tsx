import { InlineError } from "../shared/feedback/InlineError";
import { compactGhostButtonClass } from "@shiori/sdk";

/** A phone screen whose data failed to load: the error and a 「重试」 button. */
export function PhoneLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="p-3">
      <InlineError message={message} actions={<button type="button" className={compactGhostButtonClass} onClick={onRetry}>重试</button>} />
    </div>
  );
}
