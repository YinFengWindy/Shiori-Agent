import { ArrowsClockwise, GearSix } from "@phosphor-icons/react";
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
      <p role="alert" className="mb-4 mt-1 break-words rounded-md border-l-2 border-[var(--danger-300)] bg-danger-soft px-3 py-2.5 text-body-sm text-danger-text">{error}</p>
    </OnboardingCard>
  );
}
