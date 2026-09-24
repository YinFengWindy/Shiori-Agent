import { Fragment } from "react";
import { Check } from "@phosphor-icons/react";
import type { OnboardingProgress as Progress } from "./onboardingState";
import { selectOnboardingStepStatuses } from "./onboardingSteps";
import { cx } from "../shared/styles";

const dotClass = {
  done: "border-line-accent bg-accent-soft text-accent-text",
  current: "border-accent bg-white text-accent-text ring-4 ring-accent-soft",
  upcoming: "border-line bg-white/70 text-ink-faint",
} as const;

const labelClass = {
  done: "text-ink-secondary",
  current: "font-medium text-ink",
  upcoming: "text-ink-faint",
} as const;

/**
 * Small top-left step indicator: 模型 → 角色 → 开始, every step always shown
 * as done / current / upcoming. The connector after a finished step fills in
 * (token motion; reduced motion jumps).
 */
export function OnboardingProgress({ step }: { step: Progress["step"] | undefined }) {
  const steps = selectOnboardingStepStatuses(step);
  return (
    <nav aria-label="首次设置进度" className="surface-glass pointer-events-auto inline-flex items-center rounded-full px-3 py-1.5">
      <ol className="flex items-center gap-2">
        {steps.map((item, index) => (
          <Fragment key={item.id}>
            {index > 0 ? (
              <li aria-hidden="true" className="h-0.5 w-6 overflow-hidden rounded-full bg-line">
                <span className={cx(
                  "block h-full origin-left rounded-full bg-accent transition-transform duration-panel ease-drawer motion-reduce:transition-none",
                  item.status === "upcoming" ? "scale-x-0" : "scale-x-100",
                )} />
              </li>
            ) : null}
            <li aria-current={item.status === "current" ? "step" : undefined} className="flex items-center gap-1.5">
              <span className={cx("grid h-5 w-5 place-items-center rounded-full border text-caption font-semibold transition-[background-color,border-color,box-shadow,color] duration-base", dotClass[item.status])}>
                {item.status === "done" ? <Check className="h-3 w-3" weight="bold" aria-hidden="true" /> : index + 1}
              </span>
              <span className={cx("text-caption", labelClass[item.status])}>
                {item.label}
                {item.status === "done" ? <span className="sr-only">（已完成）</span> : null}
              </span>
            </li>
          </Fragment>
        ))}
      </ol>
    </nav>
  );
}
