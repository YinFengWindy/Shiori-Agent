import { toFileUrl } from "../shared/format";
import { useLayoutEffect, useRef } from "react";
import { ResetIcon } from "../shared/icons";
import { cx, inputClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";

type RoleDetailPageProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  featuredImageUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onBackToList: () => void;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders the second-level role detail page and hosts the role editor form. */
export function RoleDetailPage({
  activeRole,
  bridgeReady,
  previewAvatar,
  featuredImageUrl,
  roleForm,
  roleFormDirty,
  savingRole,
  onBackToList,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
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

  useLayoutEffect(() => {
    const textarea = promptRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [roleForm.systemPrompt]);

  return (
    <section
      className="role-detail-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-white"
      data-testid="role-detail-page"
      data-has-featured-image={featuredImageUrl ? "true" : "false"}
    >
      {featuredImageUrl ? (
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: `url("${featuredImageUrl}")` }}
          data-testid="role-illustration-hero"
        />
      ) : (
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" data-testid="role-illustration-hero" />
      )}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.04)_0%,rgba(255,255,255,0.06)_18%,rgba(255,255,255,0.18)_100%)]" />
      <div className="relative mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-8 pb-8 pt-8">
        <div className="flex items-start justify-between gap-4">
          <button
            data-testid="role-detail-back-button"
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
              onClick={onResetRoleForm}
              disabled={!roleFormDirty}
              aria-label="重置角色表单"
            >
              <ResetIcon className="h-[18px] w-[18px] fill-current" />
            </button>
            <button
              data-testid="save-role-button"
              className={cx(floatingActionClass, "border-transparent bg-white text-[#1f1f1f] hover:bg-[#F5F7FA]")}
              type="button"
              onClick={onSaveRole}
              disabled={savingRole || !roleFormDirty || !bridgeReady}
              aria-label={savingRole ? "正在保存角色" : "保存角色"}
            >
              {saveIcon}
            </button>
          </div>
        </div>
        <div className="p-2" data-testid="role-detail-info-card">
          <div className="grid gap-5 md:grid-cols-[116px_minmax(0,1fr)]">
            <button
              type="button"
              data-testid="open-role-assets-button"
              data-has-preview-avatar={previewAvatar ? "true" : "false"}
              className="group relative h-[116px] w-[116px] overflow-hidden rounded-[28px] border border-white/22 bg-[rgba(255,255,255,0.08)] text-left shadow-[0_14px_32px_rgba(15,23,42,0.14)] transition hover:scale-[1.01] focus:outline-none focus:ring-2 focus:ring-white/30"
              onClick={onOpenAssetsPage}
            >
              {previewAvatar ? (
                <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
              ) : (
                <div className="grid h-full w-full place-items-center text-[34px] font-semibold text-white">
                  {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                </div>
              )}
            </button>
            <div className="grid gap-4">
              <label className="grid gap-1.5 text-xs text-white/72">
                <span>名称</span>
                <input
                  data-testid="edit-role-name"
                  className={cx(inputClass, "border-white/16 bg-white/8 text-white placeholder:text-white/45")}
                  value={roleForm.name}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="输入角色名称"
                />
              </label>
              <label className="grid gap-1.5 text-xs text-white/72">
                <span>简介</span>
                <input
                  data-testid="edit-role-description"
                  className={cx(inputClass, "border-white/16 bg-white/8 text-white placeholder:text-white/45")}
                  value={roleForm.description}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
                  placeholder="简短描述这个角色"
                />
              </label>
              <label className="grid gap-2 text-xs text-white/72" data-testid="role-detail-form-panel">
                <span>系统提示词</span>
                <textarea
                  ref={promptRef}
                  data-testid="edit-role-prompt"
                  className={cx(inputClass, "min-h-[120px] resize-none overflow-hidden border-white/16 bg-white/8 text-white placeholder:text-white/45")}
                  value={roleForm.systemPrompt}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
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
