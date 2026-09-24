import { ArrowLeft, Trash } from "@phosphor-icons/react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { badgeClass, cx } from "../shared/styles";
import { ModelRegistrationFields } from "./ModelRegistrationFields";
import { SettingsSectionCard, settingsIconButtonClass } from "./SettingsFieldPrimitives";

type ModelRegistrationDetailsProps = {
  registration: ModelRegistrationFormData;
  /** A new entry that is not in the saved catalog yet (see `useModelRegistrationDraft`). */
  isDraft?: boolean;
  canDelete: boolean;
  onBack: () => void;
  onChange: (
    mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData,
  ) => void;
  onDelete: () => void;
};

/** Renders the focused editor for one model registration. */
export function ModelRegistrationDetails({
  registration,
  isDraft = false,
  canDelete,
  onBack,
  onChange,
  onDelete,
}: ModelRegistrationDetailsProps) {
  return (
    <section className="grid gap-3">
      <header className="flex min-h-10 items-center gap-2">
        <button
          className={cx(settingsIconButtonClass, "-ml-2")}
          type="button"
          aria-label="返回模型注册列表"
          title="返回模型注册列表"
          onClick={onBack}
        >
          <ArrowLeft className="h-4 w-4" weight="bold" />
        </button>
        <strong className="min-w-0 truncate text-title-sm text-ink">
          {registration.model || (isDraft ? "新模型" : "未填写模型")}
        </strong>
        {isDraft ? <span className={badgeClass}>未保存</span> : null}
        <span className="flex-1" />
        <button
          className={cx(settingsIconButtonClass, "hover:bg-danger-soft hover:text-danger-text disabled:cursor-not-allowed disabled:opacity-35")}
          type="button"
          aria-label={isDraft ? "放弃新模型" : "删除模型注册"}
          title={isDraft ? "放弃新模型" : "删除模型注册"}
          disabled={!canDelete}
          onClick={onDelete}
        >
          <Trash className="h-4 w-4" weight="bold" />
        </button>
      </header>
      <SettingsSectionCard>
        <ModelRegistrationFields registration={registration} onChange={onChange} />
      </SettingsSectionCard>
    </section>
  );
}
