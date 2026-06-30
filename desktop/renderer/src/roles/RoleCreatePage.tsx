import { useLayoutEffect, useRef } from "react";
import { ResetIcon } from "../shared/icons";
import { cx, inputClass } from "../shared/styles";
import type { NewRoleFormState } from "../shared/types";

type RoleCreatePageProps = {
  bridgeReady: boolean;
  creating: boolean;
  form: NewRoleFormState;
  onBackToList: () => void;
  onCreateRole: () => void;
  onResetForm: () => void;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
};

/** Renders the standalone create-role subpage inside role management. */
export function RoleCreatePage({
  bridgeReady,
  creating,
  form,
  onBackToList,
  onCreateRole,
  onResetForm,
  onUpdateForm,
}: RoleCreatePageProps) {
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const backIcon = (
    <svg viewBox="0 0 1024 1024" className="h-5 w-5 fill-[#111111]" aria-hidden="true">
      <path d="M631.04 161.941333a42.666667 42.666667 0 0 1 63.061333 57.386667l-2.474666 2.730667-289.962667 292.245333 289.706667 287.402667a42.666667 42.666667 0 0 1 2.730666 57.6l-2.474666 2.752a42.666667 42.666667 0 0 1-57.6 2.709333l-2.752-2.474667-320-317.44a42.666667 42.666667 0 0 1-2.709334-57.6l2.474667-2.752 320-322.56z" />
    </svg>
  );
  const saveIcon = (
    <svg viewBox="0 0 1024 1024" className="h-5 w-5 fill-current" aria-hidden="true">
      <path d="M382.4 876 7.4 501 43.1 465.4 380.9 803.2 983.6 149.7 1020.7 183.9Z" />
    </svg>
  );
  const floatingActionClass =
    "grid h-10 w-10 place-items-center rounded-full border bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none";
  const formDirty = Boolean(form.name.trim() || form.description.trim() || form.systemPrompt.trim());

  useLayoutEffect(() => {
    const textarea = promptRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [form.systemPrompt]);

  return (
    <section
      className="role-create-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-white"
      data-testid="role-create-page"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" />
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.88)_0%,rgba(255,255,255,0.94)_18%,rgba(255,255,255,0.98)_100%)]" />
      <div className="relative mx-auto flex min-h-full w-full max-w-[1120px] flex-col gap-5 px-8 pb-8 pt-8">
        <div className="flex items-start justify-between gap-4">
          <button
            className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] hover:shadow-[0_14px_28px_rgba(15,23,42,0.14)]"
            type="button"
            onClick={onBackToList}
            aria-label="返回角色列表"
          >
            {backIcon}
          </button>
          <div className="flex items-center gap-2.5">
            <button
              className={cx(floatingActionClass, "border-black/8 text-[#747474] hover:border-black/14 hover:bg-[#F5F7FA] hover:text-[#4f4f4f]")}
              type="button"
              onClick={onResetForm}
              disabled={!formDirty}
              aria-label="重置新建角色表单"
            >
              <ResetIcon className="h-[18px] w-[18px] fill-current" />
            </button>
            <button
              data-testid="create-role-button"
              className={cx(floatingActionClass, "border-transparent bg-white text-[#1f1f1f] hover:bg-[#F5F7FA]")}
              type="button"
              onClick={onCreateRole}
              disabled={creating || !bridgeReady}
              aria-label={creating ? "正在创建角色" : "创建角色"}
            >
              {saveIcon}
            </button>
          </div>
        </div>
        <div className="p-2">
          <div className="grid gap-5 rounded-[28px] border border-white/65 bg-white/72 p-8 shadow-[0_18px_48px_rgba(31,41,55,0.08)] backdrop-blur-[6px]">
            <div className="grid gap-4">
              <label className="grid gap-1.5 text-xs text-[#6b7280]">
                <span>名称</span>
                <input
                  data-testid="new-role-name"
                  className={inputClass}
                  value={form.name}
                  onChange={(event) => onUpdateForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="输入角色名称"
                />
              </label>
              <label className="grid gap-1.5 text-xs text-[#6b7280]">
                <span>简介</span>
                <input
                  data-testid="new-role-description"
                  className={inputClass}
                  value={form.description}
                  onChange={(event) => onUpdateForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="简短描述这个角色"
                />
              </label>
              <label className="grid gap-2 text-xs text-[#6b7280]">
                <span>系统提示词</span>
                <textarea
                  ref={promptRef}
                  data-testid="new-role-prompt"
                  className={cx(inputClass, "min-h-[120px] resize-none overflow-hidden border-[#E5E7EB] bg-white/78 text-[#1f2937] placeholder:text-[#9ca3af]")}
                  value={form.systemPrompt}
                  onChange={(event) => onUpdateForm((current) => ({ ...current, systemPrompt: event.target.value }))}
                  placeholder="定义这个角色的行为、语气和边界"
                />
              </label>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
