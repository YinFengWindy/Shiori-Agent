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
  onRememberIllustration: (roleId: string, illustration: string) => void;
  onSetActiveIllustration: (path: string) => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
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
  onRememberIllustration,
  onSetActiveIllustration,
  onUpdateRoleForm,
}: RoleDetailPreviewPanelProps) {
  const heroIllustration = activeIllustration || previewIllustrations[0] || "";
  const heroIllustrationUrl = heroIllustration ? toFileUrl(heroIllustration) : "";
  const hasHeroIllustration = Boolean(heroIllustrationUrl);
  const avatarLabel = roleForm.avatarSource || previewAvatar || "";

  return (
    <section className="grid gap-4" data-testid="role-detail-preview-panel">
      <div className={cx(cardClass, "overflow-hidden border-[#D9E0E8] bg-white/88 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")} data-testid="role-illustration-hero">
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
            <div className="inline-flex w-fit items-center rounded-full border border-white/30 bg-white/15 px-3 py-1 text-xs tracking-[0.16em] text-white/82 backdrop-blur-[3px]">
              当前立绘
            </div>
            <div className="max-w-[520px] rounded-[22px] border border-white/18 bg-[rgba(15,23,42,0.18)] px-5 py-4 backdrop-blur-[3px]">
              <div className="text-[12px] uppercase tracking-[0.16em] text-white/65">展示素材</div>
              <div className="mt-2 truncate text-sm text-white/92">
                {heroIllustration || "暂无立绘素材"}
              </div>
              <div className="mt-3 text-xs text-white/68">
                {previewIllustrations.length ? `已载入 ${previewIllustrations.length} 张立绘` : "当前未设置立绘"}
              </div>
            </div>
          </div>
        </div>
      </div>
      {previewIllustrations.length > 1 ? (
        <div className={cx(cardClass, "border-[#D9E0E8] bg-white/88 p-4 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}>
          <div className="mb-3 text-sm font-medium text-[#4D5967]">切换展示立绘</div>
          <div className="flex flex-wrap gap-3">
            {previewIllustrations.map((path, index) => {
              const isActive = path === activeIllustration || (!activeIllustration && index === 0);
              return (
                <button
                  key={path}
                  data-testid={`illustration-switch-${index}`}
                  type="button"
                  className={cx(
                    "overflow-hidden rounded-[18px] border bg-[#F4F7FA] p-0 transition",
                    isActive ? "border-[rgba(202,93,46,0.55)] shadow-[0_10px_24px_rgba(202,93,46,0.18)]" : "border-[#D9E0E8] hover:border-[#C9D4E0]",
                  )}
                  onClick={() => {
                    onSetActiveIllustration(path);
                    if (activeRoleId) {
                      onRememberIllustration(activeRoleId, path);
                    }
                  }}
                >
                  <img className="h-[96px] w-[96px] object-cover" src={toFileUrl(path)} alt="illustration thumb" />
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      <div className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-5 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")} data-testid="role-detail-info-card">
        <div className="grid gap-5 md:grid-cols-[116px_minmax(0,1fr)]">
          <div className="grid content-start gap-3">
            <div className="relative h-[116px] w-[116px] overflow-hidden rounded-[28px] border border-[#D9E0E8] bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)] shadow-[0_14px_32px_rgba(15,23,42,0.08)]" data-testid="role-avatar-card">
              {previewAvatar ? (
                <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
              ) : (
                <div className="grid h-full w-full place-items-center text-[34px] font-semibold text-[#8a3211]">
                  {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                </div>
              )}
            </div>
            <button
              data-testid="pick-avatar-button"
              className={cx("ghost-btn text-sm", ghostButtonClass)}
              type="button"
              disabled={!bridgeReady}
              onClick={onPickAvatar}
            >
              更换头像
            </button>
          </div>
          <div className="grid gap-4">
            <div>
              <div className={panelTitleClass}>角色信息</div>
              <div className="mt-2 text-sm text-[#7A8593]">维护角色名称、简介和展示素材。</div>
            </div>
            <label className={cx("grid gap-1.5 text-xs text-text", bodyTextClass)}>
              <span>名称</span>
              <input
                data-testid="edit-role-name"
                className={inputClass}
                value={roleForm.name}
                onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
              />
            </label>
            <label className={cx("grid gap-1.5 text-xs text-text", bodyTextClass)}>
              <span>简介</span>
              <input
                data-testid="edit-role-description"
                className={inputClass}
                value={roleForm.description}
                onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
              />
            </label>
            <div className="grid gap-2 rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
              <div className="truncate">头像素材：{avatarLabel || "未设置"}</div>
              <div className="truncate">当前立绘：{heroIllustration || "未设置"}</div>
            </div>
            <div className="flex gap-2.5">
              <button
                data-testid="pick-illustrations-button"
                className={cx("ghost-btn text-sm", ghostButtonClass)}
                type="button"
                disabled={!bridgeReady}
                onClick={onPickIllustrations}
              >
                更换立绘
              </button>
            </div>
          </div>
        </div>
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
  return (
    <section className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")} data-testid="role-detail-form-panel">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <div className={panelTitleClass}>系统提示词</div>
          <div className="mt-2 text-sm text-[#7A8593]">在这里维护角色的核心行为设定。</div>
        </div>
        {roleFormDirty ? <span className="rounded-full border border-[rgba(138,91,17,0.18)] bg-[rgba(138,91,17,0.08)] px-3 py-2 text-xs text-[#8a5b11]">有未保存更改</span> : null}
      </div>
      <label className={cx("grid gap-1.5 text-xs text-text", bodyTextClass)}>
        <span>系统提示词</span>
        <textarea
          data-testid="edit-role-prompt"
          className={cx("role-prompt", textareaClass, "min-h-[340px]")}
          value={roleForm.systemPrompt}
          onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
        />
      </label>
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
