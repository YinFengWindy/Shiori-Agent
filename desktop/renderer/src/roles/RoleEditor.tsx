import type React from "react";
import { toFileUrl } from "../shared/format";
import {
  bodyTextClass,
  cardClass,
  cx,
  ghostButtonClass,
  inputClass,
  panelHeadClass,
  panelTitleClass,
  primaryButtonClass,
  textareaClass,
} from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";

type RoleEditorProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeIllustration: string;
  bridgeReady: boolean;
  clearAvatar: boolean;
  clearIllustrations: boolean;
  embedded?: boolean;
  previewAvatar: string | null;
  previewIllustrations: string[];
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onSetActiveIllustration: (path: string) => void;
  onRememberIllustration: (roleId: string, illustration: string) => void;
  onPickAvatar: () => void;
  onPickIllustrations: () => void;
  onClearAvatar: () => void;
  onClearIllustrations: () => void;
  onDeleteRole: () => void;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders role metadata, prompt, and local artwork editing controls. */
export function RoleEditor({
  activeRole,
  activeRoleId,
  activeIllustration,
  bridgeReady,
  previewAvatar,
  previewIllustrations,
  embedded = false,
  roleForm,
  roleFormDirty,
  savingRole,
  onUpdateRoleForm,
  onSetActiveIllustration,
  onRememberIllustration,
  onPickAvatar,
  onPickIllustrations,
  onClearAvatar,
  onClearIllustrations,
  onDeleteRole,
  onResetRoleForm,
  onSaveRole,
}: RoleEditorProps) {
  const labelClass = cx("grid gap-1.5 text-xs text-text", bodyTextClass);
  const ghostDangerButtonClass =
    "ghost-btn danger cursor-pointer rounded-full border border-[rgba(143,43,24,0.22)] bg-[rgba(255,248,239,0.88)] px-[18px] py-3 text-[#8f2b18] disabled:cursor-default disabled:opacity-50";
  const containerClass = embedded
    ? "role-editor grid min-h-0 gap-3 rounded-[24px] border border-[#E7EBF0] bg-white/92 p-6 shadow-[0_18px_48px_rgba(31,41,55,0.08)]"
    : "role-editor scrollbar-soft scrollbar-soft-muted absolute bottom-6 right-6 top-20 z-[3] grid min-h-0 w-[calc(100%_-_48px)] max-w-[420px] grid-rows-[auto_minmax(0,1fr)] gap-3 overflow-auto rounded-[18px] border border-[#ededed] bg-white/95 p-[18px] shadow-editor";
  const contentClass = embedded
    ? "editor-form grid gap-3"
    : "editor-form grid gap-3";

  return (
    <section className={containerClass}>
      <div className={panelHeadClass}>
        <h3 className={panelTitleClass}>Role Editor</h3>
        {roleFormDirty ? <span className="dirty-chip rounded-full border border-[rgba(138,91,17,0.18)] bg-[rgba(138,91,17,0.08)] px-3 py-2 text-xs text-[#8a5b11]">Unsaved changes</span> : null}
      </div>
      {activeRole ? (
        <div className={contentClass}>
          <label className={labelClass}>
            <span>Name</span>
            <input
              data-testid="edit-role-name"
              className={inputClass}
              value={roleForm.name}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label className={labelClass}>
            <span>Description</span>
            <input
              data-testid="edit-role-description"
              className={inputClass}
              value={roleForm.description}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
            />
          </label>
          <label className={labelClass}>
            <span>System Prompt</span>
            <textarea
              data-testid="edit-role-prompt"
              className={cx("role-prompt", textareaClass, "min-h-40")}
              value={roleForm.systemPrompt}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
            />
          </label>
          <div className="asset-actions flex flex-wrap gap-2.5">
            <button data-testid="pick-avatar-button" className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onPickAvatar} disabled={!bridgeReady}>
              Pick Avatar
            </button>
            <button data-testid="pick-illustrations-button" className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onPickIllustrations} disabled={!bridgeReady}>
              Pick Illustrations
            </button>
            <button data-testid="clear-avatar-button" className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onClearAvatar} disabled={!bridgeReady}>
              Clear Avatar
            </button>
            <button data-testid="clear-illustrations-button" className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onClearIllustrations} disabled={!bridgeReady}>
              Clear Illustrations
            </button>
            <button className={ghostDangerButtonClass} type="button" onClick={onDeleteRole} disabled={!bridgeReady}>
              Delete Role
            </button>
          </div>
          {previewAvatar ? (
            <img
              className="editor-avatar mb-3 block h-[72px] w-[72px] rounded-2xl border border-stroke object-cover"
              src={toFileUrl(previewAvatar)}
              alt={`${activeRole.name} avatar`}
            />
          ) : null}
          {previewIllustrations.length ? (
            <div className="illustration-strip flex flex-wrap gap-2.5">
              {previewIllustrations.map((path) => (
                <button
                  key={path}
                  type="button"
                  className={cx(
                    "illustration-thumb h-[88px] w-[88px] overflow-hidden rounded-2xl border border-stroke bg-[rgba(255,252,246,0.95)] p-0",
                    path === activeIllustration && "active border-[rgba(202,93,46,0.5)]",
                  )}
                  onClick={() => {
                    onSetActiveIllustration(path);
                    if (activeRoleId) {
                      onRememberIllustration(activeRoleId, path);
                    }
                  }}
                >
                  <img className="block h-full w-full object-cover" src={toFileUrl(path)} alt="illustration thumb" />
                </button>
              ))}
            </div>
          ) : null}
          {roleForm.avatarSource ? <div className="asset-preview rounded-[14px] border border-dashed border-stroke bg-[rgba(255,252,246,0.74)] px-3.5 py-3 text-muted">Avatar: {roleForm.avatarSource}</div> : null}
          {roleForm.illustrationSources.length ? (
            <div className="asset-preview rounded-[14px] border border-dashed border-stroke bg-[rgba(255,252,246,0.74)] px-3.5 py-3 text-muted">
              Illustrations:
              <ul className="mb-0 mt-2 list-disc pl-5">
                {roleForm.illustrationSources.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          <div className="editor-actions flex gap-2.5">
            <button className={cx("ghost-btn", ghostButtonClass)} type="button" onClick={onResetRoleForm} disabled={!roleFormDirty}>
              Reset
            </button>
            <button data-testid="save-role-button" className={cx("primary-btn text-sm", primaryButtonClass)} type="button" onClick={onSaveRole} disabled={savingRole || !activeRoleId || !roleFormDirty || !bridgeReady}>
              {savingRole ? "Saving..." : "Save Role"}
            </button>
          </div>
        </div>
      ) : (
        <div className={cx("empty-card", cardClass, "p-4")}>Select a role to edit its prompt and local artwork.</div>
      )}
    </section>
  );
}
