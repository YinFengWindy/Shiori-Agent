import { CaretRight, Plus } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { modelEffortLabels } from "../shared/modelEffortLabels";

type ModelRegistrationListProps = {
  registrations: ModelRegistrationFormData[];
  onCreate: () => void;
  onOpen: (registrationId: string) => void;
};

function registrationInitials(registration: ModelRegistrationFormData): string {
  const source = registration.model || registration.provider || "M";
  const initials = source
    .split(/[\s._/-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return initials || "M";
}

/** Renders compact model registration previews and the create action. */
export function ModelRegistrationList({
  registrations,
  onCreate,
  onOpen,
}: ModelRegistrationListProps) {
  return (
    <section className="grid gap-3">
      <div className="flex justify-end">
        <button
          className="grid h-8 w-8 place-items-center rounded-md border border-line-soft bg-white text-ink-secondary transition hover:border-line-strong hover:bg-surface-soft focus:outline-none"
          type="button"
          aria-label="新建模型注册"
          title="新建模型注册"
          onClick={onCreate}
        >
          <Plus className="h-3.5 w-3.5" weight="bold" />
        </button>
      </div>
      <div className="grid gap-3">
        {registrations.map((registration) => (
          <button
            className="group grid min-h-[84px] w-full grid-cols-[40px_minmax(0,1fr)_auto] items-center gap-3 rounded-md border border-line-soft bg-white px-3 py-2.5 text-left transition hover:border-accent hover:bg-accent-softer focus:outline-none"
            type="button"
            key={registration.id}
            onClick={() => onOpen(registration.id)}
          >
            <span className="grid h-10 w-10 place-items-center rounded-md border border-line-soft bg-surface-soft text-[11px] font-semibold text-ink-muted">
              {registrationInitials(registration)}
            </span>
            <span className="min-w-0">
              <strong className="block truncate text-[13px] font-semibold text-ink">
                {registration.model || "未配置模型"}
              </strong>
              <span className="mt-1 block truncate text-[13px] text-accent-text">
                {registration.baseUrl || "未配置 Base URL"}
              </span>
            </span>
            <span className="flex items-center gap-2.5 pl-2">
              <span className="hidden text-right sm:block">
                <span className="block text-[11px] font-medium text-ink-muted">
                  {registration.provider || "未配置 Provider"}
                </span>
                <span className="mt-1 block text-[11px] text-ink-faint">
                  {modelEffortLabels[registration.effort]}
                </span>
              </span>
              <CaretRight className="h-3.5 w-3.5 text-ink-faint transition group-hover:translate-x-0.5 group-hover:text-accent-text" weight="bold" />
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
