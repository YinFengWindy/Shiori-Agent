import { CheckIcon, CopyIcon, KeyIcon } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { cardClass, compactGhostButtonClass, compactPrimaryButtonClass, cx } from "../shared/styles";
import { useCopyText } from "../shared/useCopyText";
import { formatCountdown } from "./identityPresentation";

/**
 * The pairing card: the shown code with copy and countdown, and the action
 * that generates one (again). With no code shown it is the action alone.
 */
export function PairingCodePanel({ code, remainingMs, busy, error, onCreate }: {
  code: string | null;
  remainingMs: number;
  busy: boolean;
  error: string;
  onCreate: () => void;
}) {
  const { copied, copy } = useCopyText();
  return <section className={cx(cardClass, "grid gap-4 p-5")} aria-label="配对码">
    {code ? <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="grid min-w-0 gap-1">
        <span className="text-body-sm text-ink-secondary">配对码</span>
        <span className="select-all font-mono text-display tracking-widest text-ink" data-testid="pairing-code">{code}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-body-sm tabular-nums text-ink-muted" role="timer" aria-label="剩余时间">{formatCountdown(remainingMs)}</span>
        <button type="button" className={compactGhostButtonClass} onClick={() => void copy(code)}>
          {copied ? <CheckIcon className="h-4 w-4 text-success-text" weight="bold" aria-hidden="true" /> : <CopyIcon className="h-4 w-4" aria-hidden="true" />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
    </div> : null}
    <div className={cx("flex", code && "border-t border-line-soft pt-4")}>
      <button type="button" className={compactPrimaryButtonClass} disabled={busy} onClick={onCreate}>
        <KeyIcon className="h-4 w-4" aria-hidden="true" />{code ? "重新生成" : "生成配对码"}
      </button>
    </div>
    {error ? <InlineError message={error} /> : null}
  </section>;
}
