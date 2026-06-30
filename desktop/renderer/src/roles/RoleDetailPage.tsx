import { toFileUrl } from "../shared/format";
import { bodyTextClass, cx, inputClass, panelTitleClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { useState } from "react";

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
  activeIllustration,
  activeRole,
  activeRoleId,
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
  const [editingName, setEditingName] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState(false);
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
  const resetIcon = (
    <span
      className="relative h-[13px] w-[13px] before:absolute before:inset-[1px] before:rounded-full before:border-[1.3px] before:border-current before:border-r-transparent before:content-[''] after:absolute after:right-[0.5px] after:top-[1px] after:h-[4px] after:w-[4px] after:rotate-45 after:border-r-[1.3px] after:border-t-[1.3px] after:border-current after:content-['']"
      aria-hidden="true"
    />
  );
  const floatingActionClass =
    "grid h-10 w-10 place-items-center rounded-full border bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none";

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
              {resetIcon}
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
              <div>
                {editingName ? (
                  <input
                    data-testid="edit-role-name"
                    className={cx(inputClass, "max-w-[420px] border-white/16 bg-transparent px-0 py-0 text-[34px] font-semibold leading-none text-white placeholder:text-white/45")}
                    value={roleForm.name}
                    onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
                    onBlur={() => setEditingName(false)}
                    autoFocus
                  />
                ) : (
                  <button
                    type="button"
                    className={cx(panelTitleClass, "text-left text-[34px] leading-none text-white")}
                    onClick={() => setEditingName(true)}
                  >
                    {roleForm.name || "点击填写角色名称"}
                  </button>
                )}
                {editingDescription ? (
                  <input
                    data-testid="edit-role-description"
                    className={cx(inputClass, "mt-3 border-white/16 bg-transparent text-sm text-white placeholder:text-white/45")}
                    value={roleForm.description}
                    onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
                    onBlur={() => setEditingDescription(false)}
                    autoFocus
                  />
                ) : (
                  <button
                    type="button"
                    className="mt-3 text-left text-sm leading-6 text-white/86"
                    onClick={() => setEditingDescription(true)}
                  >
                    {roleForm.description || "点击填写角色简介"}
                  </button>
                )}
              </div>
              <div className={cx("grid gap-2 text-xs text-white/72", bodyTextClass)} data-testid="role-detail-form-panel">
                <div className="uppercase tracking-[0.14em]">系统提示词</div>
                {editingPrompt ? (
                  <textarea
                    data-testid="edit-role-prompt"
                    className={cx(inputClass, "min-h-[220px] resize-y border-white/16 bg-transparent text-white placeholder:text-white/45")}
                    value={roleForm.systemPrompt}
                    onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
                    onBlur={() => setEditingPrompt(false)}
                    autoFocus
                  />
                ) : (
                  <button
                    type="button"
                    className="text-left text-sm leading-7 text-white/86"
                    onClick={() => setEditingPrompt(true)}
                  >
                    {roleForm.systemPrompt || "点击填写系统提示词"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
