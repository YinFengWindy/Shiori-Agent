import { toFileUrl } from "../shared/format";
import {
  bodyTextClass,
  cardClass,
  cx,
  ghostButtonClass,
  inputClass,
  panelTitleClass,
  primaryButtonClass,
  textareaClass,
} from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";

type RoleDetailPreviewPanelProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  previewIllustrations: string[];
  roleForm: RoleFormState;
  onPickAvatar: () => void;
  onPickIllustrations: () => void;
  onRemoveAvatar: () => void;
  onRemoveIllustration: (path: string) => void;
  onRememberIllustration: (roleId: string, illustration: string) => void;
  onSetActiveIllustration: (path: string) => void;
};

type RoleDetailFormPanelProps = {
  bridgeReady: boolean;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
};

type RoleDangerZoneProps = {
  bridgeReady: boolean;
  onDeleteRole: () => void;
};

export function RoleDetailPreviewPanel({
  activeIllustration,
  activeRole,
  activeRoleId,
  bridgeReady,
  previewAvatar,
  previewIllustrations,
  roleForm,
  onPickAvatar,
  onPickIllustrations,
  onRemoveAvatar,
  onRemoveIllustration,
  onRememberIllustration,
  onSetActiveIllustration,
}: RoleDetailPreviewPanelProps) {
  const heroIllustration = activeIllustration || previewIllustrations[0] || "";
  const heroIllustrationUrl = heroIllustration ? toFileUrl(heroIllustration) : "";
  const hasHeroIllustration = Boolean(heroIllustrationUrl);
  const avatarLabel = roleForm.avatarSource || previewAvatar || "";

  return (
    <section className="grid gap-4" data-testid="role-detail-preview-panel">
      <div className={cx(cardClass, "overflow-hidden border-[#D9E0E8] bg-white/88 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
        <div className="relative min-h-[420px]">
          {hasHeroIllustration ? (
            <>
              <div
                className="absolute inset-0 bg-cover bg-center bg-no-repeat"
                style={{ backgroundImage: `url("${heroIllustrationUrl}")` }}
              />
              <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.08)_0%,rgba(255,255,255,0.12)_34%,rgba(15,23,42,0.68)_100%)]" />
            </>
          ) : (
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" />
          )}
          <div className="relative z-[1] flex min-h-[420px] flex-col justify-between p-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className={cx("truncate text-[30px] font-semibold leading-none", hasHeroIllustration ? "text-white" : "text-[#1f1f1f]")}>
                  {activeRole ? activeRole.name : "角色详情"}
                </div>
                <div className={cx(bodyTextClass, "mt-3 max-w-[320px] text-sm leading-6", hasHeroIllustration ? "text-white/88" : "text-[#617080]")}>
                  {activeRole?.description || "编辑当前角色的设定、头像和立绘素材。"}
                </div>
              </div>
              <button
                data-testid="pick-illustrations-button"
                className={cx("ghost-btn text-sm", ghostButtonClass)}
                type="button"
                disabled={!bridgeReady}
                onClick={onPickIllustrations}
              >
                选择插图
              </button>
            </div>
            <div className="flex items-end gap-4">
              <div className="relative h-[108px] w-[108px] overflow-hidden rounded-[28px] border border-white/35 bg-white/80 shadow-[0_14px_32px_rgba(15,23,42,0.18)]" data-testid="role-avatar-card">
                {previewAvatar ? (
                  <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
                ) : (
                  <div className="grid h-full w-full place-items-center text-[30px] font-semibold text-[#8a3211]">
                    {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                  </div>
                )}
                <button
                  data-testid="remove-avatar-button"
                  className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full border border-white/60 bg-[rgba(15,23,42,0.58)] text-sm text-white transition hover:bg-[rgba(15,23,42,0.74)] disabled:cursor-default disabled:opacity-40"
                  type="button"
                  disabled={!bridgeReady || (!previewAvatar && !roleForm.avatarSource)}
                  onClick={onRemoveAvatar}
                  aria-label="删除头像"
                >
                  ×
                </button>
              </div>
              <div className="min-w-0 flex-1 rounded-[22px] border border-white/20 bg-[rgba(255,255,255,0.14)] px-4 py-3 backdrop-blur-[2px]">
                <div className={cx("text-xs uppercase tracking-[0.16em]", hasHeroIllustration ? "text-white/65" : "text-[#7A8593]")}>当前素材</div>
                <div className={cx("mt-2 truncate text-sm", hasHeroIllustration ? "text-white/92" : "text-[#43505D]")}>
                  {heroIllustration || avatarLabel || "暂无预览素材"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className={cx(cardClass, "border-[#D9E0E8] bg-white/88 p-5 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div className={panelTitleClass}>素材库</div>
          <button
            data-testid="pick-avatar-button"
            className={cx("ghost-btn text-sm", ghostButtonClass)}
            type="button"
            disabled={!bridgeReady}
            onClick={onPickAvatar}
          >
            选择头像
          </button>
        </div>
        {previewIllustrations.length ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-3">
            {previewIllustrations.map((path) => {
              const isActive = path === activeIllustration;
              return (
                <div key={path} className="relative">
                  <button
                    data-testid={`illustration-thumb-${path}`}
                    type="button"
                    className={cx(
                      "group w-full overflow-hidden rounded-[20px] border bg-[#F4F7FA] p-0 text-left transition",
                      isActive ? "border-[rgba(202,93,46,0.55)] shadow-[0_10px_24px_rgba(202,93,46,0.18)]" : "border-[#D9E0E8] hover:border-[#C9D4E0]",
                    )}
                    onClick={() => {
                      onSetActiveIllustration(path);
                      if (activeRoleId) {
                        onRememberIllustration(activeRoleId, path);
                      }
                    }}
                  >
                    <img className="h-[128px] w-full object-cover" src={toFileUrl(path)} alt="illustration thumb" />
                  </button>
                  <button
                    data-testid={`remove-illustration-${path}`}
                    className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full border border-white/60 bg-[rgba(15,23,42,0.58)] text-sm text-white transition hover:bg-[rgba(15,23,42,0.74)] disabled:cursor-default disabled:opacity-40"
                    type="button"
                    disabled={!bridgeReady}
                    onClick={() => onRemoveIllustration(path)}
                    aria-label="删除插图"
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="grid min-h-[132px] place-items-center rounded-[20px] border border-dashed border-[#D9E0E8] bg-[#F7FAFD] text-sm text-[#74808D]">
            暂无插图素材
          </div>
        )}
      </div>
    </section>
  );
}

export function RoleDetailFormPanel({
  bridgeReady,
  roleForm,
  roleFormDirty,
  savingRole,
  onResetRoleForm,
  onSaveRole,
  onUpdateRoleForm,
}: RoleDetailFormPanelProps) {
  const labelClass = cx("grid gap-1.5 text-xs text-text", bodyTextClass);

  return (
    <section className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")} data-testid="role-detail-form-panel">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <div className={panelTitleClass}>角色设定</div>
          <div className="mt-2 text-sm text-[#7A8593]">在这里维护名称、简介和系统提示词。</div>
        </div>
        {roleFormDirty ? <span className="rounded-full border border-[rgba(138,91,17,0.18)] bg-[rgba(138,91,17,0.08)] px-3 py-2 text-xs text-[#8a5b11]">有未保存更改</span> : null}
      </div>
      <div className="grid gap-4">
        <label className={labelClass}>
          <span>名称</span>
          <input
            data-testid="edit-role-name"
            className={inputClass}
            value={roleForm.name}
            onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
          />
        </label>
        <label className={labelClass}>
          <span>简介</span>
          <input
            data-testid="edit-role-description"
            className={inputClass}
            value={roleForm.description}
            onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
          />
        </label>
        <label className={labelClass}>
          <span>系统提示词</span>
          <textarea
            data-testid="edit-role-prompt"
            className={cx("role-prompt", textareaClass, "min-h-[340px]")}
            value={roleForm.systemPrompt}
            onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
          />
        </label>
      </div>
      <div className="mt-6 flex gap-2.5">
        <button className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onResetRoleForm} disabled={!roleFormDirty}>
          重置
        </button>
        <button data-testid="save-role-button" className={cx("primary-btn text-sm", primaryButtonClass)} type="button" onClick={onSaveRole} disabled={savingRole || !roleFormDirty || !bridgeReady}>
          {savingRole ? "保存中..." : "保存角色"}
        </button>
      </div>
    </section>
  );
}

export function RoleDangerZone({
  bridgeReady,
  onDeleteRole,
}: RoleDangerZoneProps) {
  return (
    <section className={cx(cardClass, "border-[rgba(143,43,24,0.2)] bg-[rgba(255,248,239,0.88)] p-5")} data-testid="role-danger-zone">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className={panelTitleClass}>危险操作</div>
          <div className="mt-2 text-sm text-[#8f4d3c]">删除角色会同时移除角色会话与相关素材。</div>
        </div>
        <button
          className="ghost-btn danger cursor-pointer rounded-full border border-[rgba(143,43,24,0.22)] bg-[rgba(255,248,239,0.88)] px-[18px] py-3 text-[#8f2b18] disabled:cursor-default disabled:opacity-50"
          type="button"
          onClick={onDeleteRole}
          disabled={!bridgeReady}
        >
          删除角色
        </button>
      </div>
    </section>
  );
}
