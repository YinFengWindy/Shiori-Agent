import { CaretRight, Plus } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";

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
          className="grid h-9 w-9 place-items-center rounded-md border border-[#D8DFE7] bg-white text-[#344054] transition hover:border-[#B9C6D4] hover:bg-[#F7F9FB] focus:outline-none"
          type="button"
          aria-label="新建模型注册"
          title="新建模型注册"
          onClick={onCreate}
        >
          <Plus className="h-4 w-4" weight="bold" />
        </button>
      </div>
      <div className="grid gap-3">
        {registrations.map((registration) => (
          <button
            className="group grid min-h-[92px] w-full grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-4 rounded-md border border-[#DDE4EC] bg-white px-4 py-3 text-left transition hover:border-[#9FC5E8] hover:bg-[#F7FBFF] focus:outline-none"
            type="button"
            key={registration.id}
            onClick={() => onOpen(registration.id)}
          >
            <span className="grid h-11 w-11 place-items-center rounded-md border border-[#DDE4EC] bg-[#F7F9FB] text-xs font-semibold text-[#667085]">
              {registrationInitials(registration)}
            </span>
            <span className="min-w-0">
              <strong className="block truncate text-sm font-semibold text-[#182230]">
                {registration.model || "未配置模型"}
              </strong>
              <span className="mt-1 block truncate text-sm text-[#1976D2]">
                {registration.baseUrl || "未配置 Base URL"}
              </span>
            </span>
            <span className="flex items-center gap-3 pl-2">
              <span className="hidden text-right sm:block">
                <span className="block text-xs font-medium text-[#667085]">
                  {registration.provider || "未配置 Provider"}
                </span>
                <span className="mt-1 block text-xs text-[#98A2B3]">
                  {registration.effort}
                </span>
              </span>
              <CaretRight className="h-4 w-4 text-[#98A2B3] transition group-hover:translate-x-0.5 group-hover:text-[#1976D2]" weight="bold" />
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
