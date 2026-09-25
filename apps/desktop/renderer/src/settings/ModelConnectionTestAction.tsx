import { CheckCircle, CircleNotch, PlugsConnected } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { cx, pressableClass } from "../shared/styles";
import type { ModelConnectionTestOutcome } from "./modelConnectionTest";
import { useModelConnectionTest } from "./useModelConnectionTest";

const testButtonClass = cx(
  pressableClass,
  "inline-flex min-h-9 shrink-0 cursor-pointer items-center gap-2 rounded-md border border-line bg-surface px-3.5 py-2 text-body-sm text-ink-secondary hover:border-line-accent hover:bg-accent-softer hover:text-accent-text disabled:cursor-default disabled:opacity-50",
);

/** Probes the draft connection with one tiny request and shows the result beside the action. */
export function ModelConnectionTestAction({ registration, onTested }: {
  registration: ModelRegistrationFormData;
  onTested?: (outcome: ModelConnectionTestOutcome) => void;
}) {
  const { view, run } = useModelConnectionTest(registration, onTested);
  const testing = view.status === "testing";
  return (
    <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
      <button type="button" className={testButtonClass} disabled={testing || !registration.model.trim()} onClick={() => void run()}>
        {testing
          ? <CircleNotch className="h-4 w-4 motion-safe:animate-spin" weight="bold" aria-hidden="true" />
          : <PlugsConnected className="h-4 w-4" weight="bold" aria-hidden="true" />}
        {testing ? "正在测试" : "测试连接"}
      </button>
      {/* A failure (her line + the provider's message) keeps a readable width: beside the button when it fits, else on its own row. */}
      <div role="status" className={cx("min-w-0 flex-1 self-center", view.status === "failure" && "min-w-[16rem]")}>
        {view.status === "success" ? (
          <span className="inline-flex items-center gap-1.5 text-body-sm text-success-text">
            <CheckCircle className="h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />连接成功 · {view.latencyMs} ms
          </span>
        ) : null}
        {view.status === "failure" ? <InlineError role={false} persona="connectionTestFailed" message={view.message} /> : null}
      </div>
    </div>
  );
}
