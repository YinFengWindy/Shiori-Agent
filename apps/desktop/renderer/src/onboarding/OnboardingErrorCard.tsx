import { ArrowsClockwise, GearSix } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { OnboardingCard } from "./OnboardingCard";
import { onboardingSecondaryClass } from "./onboardingStyles";

/** The guide's inline error area: the failure, a retry, and the model settings way out. */
export function OnboardingErrorCard({ title, error, retrying, disabled, onRetry, onOpenSettings }: {
  title: string;
  error: string;
  retrying: boolean;
  disabled: boolean;
  onRetry: () => void;
  onOpenSettings: () => void;
}) {
  return (
    <OnboardingCard title={title} footer={<>
      <button type="button" className={onboardingSecondaryClass} disabled={disabled} onClick={onOpenSettings}>
        <GearSix className="h-4 w-4" aria-hidden="true" />模型注册设置
      </button>
      <button type="button" className={onboardingSecondaryClass} disabled={retrying || disabled} onClick={onRetry}>
        <ArrowsClockwise className="h-4 w-4" aria-hidden="true" />重试连接
      </button>
    </>}>
      <InlineError className="mb-4 mt-1" message={error} />
    </OnboardingCard>
  );
}
