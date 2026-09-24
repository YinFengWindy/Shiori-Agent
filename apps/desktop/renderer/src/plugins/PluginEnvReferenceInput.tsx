import { WarningCircle } from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { readEnvReference } from "./jsonSchemaForm";

/**
 * Wraps a text or secret control for a value that may be an unexpanded
 * `${NAME}` reference. Such a value is shown as the reference itself — never
 * as masked dots that would read as a filled-in secret — with a way to type
 * a literal value instead. The draft keeps the reference until something is
 * actually typed, so opening the input and leaving it empty changes nothing.
 */
export function PluginEnvReferenceInput({ value, label, renderInput }: {
  value: unknown;
  label: string;
  /** The ordinary control; `displayValue` is "" while a reference is being replaced. */
  renderInput: (displayValue: string, onBlurEmpty: () => void) => ReactNode;
}) {
  const [replacing, setReplacing] = useState(false);
  const reference = readEnvReference(value);
  if (!reference) return <>{renderInput(String(value ?? ""), () => undefined)}</>;
  if (replacing) return <>{renderInput("", () => setReplacing(false))}</>;
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      <div className="grid min-w-0 flex-1 gap-0.5 rounded-md border border-dashed border-line bg-surface-soft px-2.5 py-1.5">
        <span className="truncate text-body-sm text-ink">
          引用环境变量 <code className="font-mono text-accent-text">{reference}</code>
        </span>
        <span className="flex items-center gap-1 text-caption text-warning-text">
          <WarningCircle className="h-3.5 w-3.5 shrink-0" weight="bold" aria-hidden="true" />
          当前环境中未设置
        </span>
      </div>
      <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={() => setReplacing(true)}>
        改为直接填写
      </button>
    </div>
  );
}
