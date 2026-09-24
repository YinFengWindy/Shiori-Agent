import { CaretRight, Plus } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortLabels } from "../shared/modelEffortLabels";
import { badgeClass, cardClass, compactButtonSizeClass, cx, pressableClass, primaryButtonSurfaceClass } from "../shared/styles";
import { registrationHost, registrationInitials, registrationProviderLabel } from "./modelRegistrationSummary";

type ModelRegistrationListProps = {
  registrations: ModelRegistrationFormData[];
  onCreate: () => void;
  onOpen: (registrationId: string) => void;
};

/** Renders compact model registration previews and the create action. */
export function ModelRegistrationList({
  registrations,
  onCreate,
  onOpen,
}: ModelRegistrationListProps) {
  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <span className="px-1 text-body-sm font-semibold text-ink-secondary">{registrations.length} 个模型</span>
        <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onCreate}>
          <Plus className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          添加模型
        </button>
      </div>
      <div className="grid gap-2.5">
        {registrations.map((registration) => {
          const provider = registrationProviderLabel(registration);
          const host = registrationHost(registration);
          return (
            <button
              className={cx(
                cardClass,
                pressableClass,
                "group grid min-h-[72px] w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left hover:border-line-accent hover:bg-accent-softer",
              )}
              type="button"
              key={registration.id}
              onClick={() => onOpen(registration.id)}
            >
              <span className="grid h-10 w-10 place-items-center rounded-md bg-accent-softer text-caption font-semibold text-accent-text" aria-hidden="true">
                {registrationInitials(registration)}
              </span>
              <span className="grid min-w-0 gap-0.5">
                <strong className="truncate text-body font-semibold text-ink">
                  {registration.model || "未填写模型"}
                </strong>
                <span className="truncate text-caption text-ink-muted">
                  {[provider, host].filter(Boolean).join(" · ") || "未填写服务地址"}
                </span>
              </span>
              <span className="flex items-center gap-2.5 pl-2">
                {registration.effort !== "none" ? (
                  <span className="hidden sm:block"><span className={badgeClass}>思考 {modelEffortLabels[registration.effort]}</span></span>
                ) : null}
                <CaretRight className="h-3.5 w-3.5 text-ink-muted transition-transform motion-safe:group-hover:translate-x-0.5" weight="bold" aria-hidden="true" />
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
