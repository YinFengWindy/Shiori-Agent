import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { useRoleModelSelection, type RoleModelSelectionChange } from "../chat/useRoleModelSelection";
import { feedback } from "../shared/feedback/feedbackStore";
import { modelEffortOptions } from "../shared/modelEffortLabels";
import { Select, type SelectOption } from "../shared/ui/Select";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";

type RoleModelSectionProps = {
  roleId: string;
  /** The role's `updated_at`; a save elsewhere re-reads the binding. */
  roleRevision: string;
  bridgeReady: boolean;
  /** Called after a change was applied, so the app's role snapshot catches up. */
  onChanged: () => void;
};

const changeNotices: Record<RoleModelSelectionChange, string> = {
  dialogue: "聊天模型已切换",
  visual: "识图模型已切换",
  dialogueEffort: "思考强度已更新",
  visualEffort: "识图思考强度已更新",
};

function registrationOptions(registrations: ModelRegistrationFormData[]): SelectOption[] {
  return registrations.map((registration) => ({ value: registration.id, label: registration.model }));
}

/**
 * The role's chat model, vision model and their reasoning effort, the same
 * binding the composer's model menu edits (`useRoleModelSelection`). Like the
 * menu, a change applies at once instead of waiting for the page's 保存.
 */
export function RoleModelSection({ roleId, roleRevision, bridgeReady, onChanged }: RoleModelSectionProps) {
  const { registrations, selection, update } = useRoleModelSelection(roleId, bridgeReady, roleRevision);
  const models = registrationOptions(registrations);
  const disabled = !bridgeReady || !selection;
  const dialogueOptions = selection?.dialogueId ? models : [{ value: "", label: "未选择" }, ...models];

  async function change(kind: RoleModelSelectionChange, value: string): Promise<void> {
    if (!(await update(kind, value))) return;
    feedback.success(changeNotices[kind]);
    onChanged();
  }

  return (
    <RoleEditorSection title="模型" data-testid="role-model-section">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={roleFieldLabelClass}>
          <span>聊天模型</span>
          <Select aria-label="聊天模型" className={roleFieldClass} disabled={disabled} value={selection?.dialogueId ?? ""} options={dialogueOptions} onValueChange={(value) => void change("dialogue", value)} />
        </label>
        <label className={roleFieldLabelClass}>
          <span>思考强度</span>
          <Select aria-label="思考强度" className={roleFieldClass} disabled={disabled || !selection?.dialogueId} value={selection?.dialogueEffort ?? "none"} options={modelEffortOptions} onValueChange={(value) => void change("dialogueEffort", value)} />
        </label>
        <label className={roleFieldLabelClass}>
          <span>识图模型</span>
          <Select aria-label="识图模型" className={roleFieldClass} disabled={disabled} value={selection?.visualId ?? ""} options={[{ value: "", label: "沿用聊天模型" }, ...models]} onValueChange={(value) => void change("visual", value)} />
        </label>
        {selection?.visualId ? (
          <label className={roleFieldLabelClass}>
            <span>识图思考强度</span>
            <Select aria-label="识图思考强度" className={roleFieldClass} disabled={disabled} value={selection.visualEffort} options={modelEffortOptions} onValueChange={(value) => void change("visualEffort", value)} />
          </label>
        ) : null}
      </div>
    </RoleEditorSection>
  );
}
