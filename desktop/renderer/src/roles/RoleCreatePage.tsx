import { cx, ghostButtonClass, inputClass, panelTitleClass, primaryButtonClass, textareaClass } from "../shared/styles";
import type { NewRoleFormState } from "../shared/types";

type RoleCreatePageProps = {
  bridgeReady: boolean;
  creating: boolean;
  form: NewRoleFormState;
  onBackToList: () => void;
  onCreateRole: () => void;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
};

/** Renders the standalone create-role subpage inside role management. */
export function RoleCreatePage({
  bridgeReady,
  creating,
  form,
  onBackToList,
  onCreateRole,
  onUpdateForm,
}: RoleCreatePageProps) {
  return (
    <section
      className="role-create-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(248,249,252,0.98)_100%)]"
      data-testid="role-create-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-8 pb-10 pt-10">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <button
              className={cx("ghost-btn mb-3 px-3 py-2 text-sm", ghostButtonClass)}
              type="button"
              onClick={onBackToList}
            >
              返回角色列表
            </button>
            <div className={cx(panelTitleClass, "text-[28px] text-[#1f1f1f]")}>新建角色</div>
            <div className="mt-2 text-sm text-[#7a7a7a]">创建一个新的角色，并填写它的基础信息与系统提示词。</div>
          </div>
        </div>
        <div className="grid max-w-[720px] gap-3 rounded-[24px] border border-[#E7EBF0] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]">
          <label className="grid gap-1.5 text-xs text-[#1f1f1f]">
            <span>名称</span>
            <input
              data-testid="new-role-name"
              className={inputClass}
              value={form.name}
              onChange={(event) => onUpdateForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="输入角色名称"
            />
          </label>
          <label className="grid gap-1.5 text-xs text-[#1f1f1f]">
            <span>简介</span>
            <input
              data-testid="new-role-description"
              className={inputClass}
              value={form.description}
              onChange={(event) => onUpdateForm((current) => ({ ...current, description: event.target.value }))}
              placeholder="简短描述这个角色"
            />
          </label>
          <label className="grid gap-1.5 text-xs text-[#1f1f1f]">
            <span>系统提示词</span>
            <textarea
              data-testid="new-role-prompt"
              className={cx(textareaClass, "min-h-40")}
              value={form.systemPrompt}
              onChange={(event) => onUpdateForm((current) => ({ ...current, systemPrompt: event.target.value }))}
              placeholder="定义这个角色的行为、语气和边界"
            />
          </label>
          <div className="flex items-center gap-2.5">
            <button
              className={cx("ghost-btn text-sm", ghostButtonClass)}
              type="button"
              onClick={onBackToList}
            >
              取消
            </button>
            <button
              data-testid="create-role-button"
              className={cx("primary-btn text-sm", primaryButtonClass)}
              type="button"
              onClick={onCreateRole}
              disabled={creating || !bridgeReady}
            >
              {creating ? "Creating..." : "Create Role"}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
