import type React from "react";
import { toFileUrl } from "../shared/format";
import type { RoleFormState, RoleRecord } from "../shared/types";

type RoleEditorProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeIllustration: string;
  bridgeReady: boolean;
  clearAvatar: boolean;
  clearIllustrations: boolean;
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
  return (
    <section className="role-editor">
      <div className="panel-head">
        <h3>Role Editor</h3>
        {roleFormDirty ? <span className="dirty-chip">Unsaved changes</span> : null}
      </div>
      {activeRole ? (
        <div className="editor-form">
          <label>
            <span>Name</span>
            <input
              data-testid="edit-role-name"
              value={roleForm.name}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label>
            <span>Description</span>
            <input
              data-testid="edit-role-description"
              value={roleForm.description}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
            />
          </label>
          <label>
            <span>System Prompt</span>
            <textarea
              data-testid="edit-role-prompt"
              className="role-prompt"
              value={roleForm.systemPrompt}
              onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
            />
          </label>
          <div className="asset-actions">
            <button data-testid="pick-avatar-button" className="ghost-btn" type="button" onClick={onPickAvatar} disabled={!bridgeReady}>
              Pick Avatar
            </button>
            <button data-testid="pick-illustrations-button" className="ghost-btn" type="button" onClick={onPickIllustrations} disabled={!bridgeReady}>
              Pick Illustrations
            </button>
            <button data-testid="clear-avatar-button" className="ghost-btn" type="button" onClick={onClearAvatar} disabled={!bridgeReady}>
              Clear Avatar
            </button>
            <button data-testid="clear-illustrations-button" className="ghost-btn" type="button" onClick={onClearIllustrations} disabled={!bridgeReady}>
              Clear Illustrations
            </button>
            <button className="ghost-btn danger" type="button" onClick={onDeleteRole} disabled={!bridgeReady}>
              Delete Role
            </button>
          </div>
          {previewAvatar ? (
            <img
              className="editor-avatar"
              src={toFileUrl(previewAvatar)}
              alt={`${activeRole.name} avatar`}
            />
          ) : null}
          {previewIllustrations.length ? (
            <div className="illustration-strip">
              {previewIllustrations.map((path) => (
                <button
                  key={path}
                  type="button"
                  className={`illustration-thumb${path === activeIllustration ? " active" : ""}`}
                  onClick={() => {
                    onSetActiveIllustration(path);
                    if (activeRoleId) {
                      onRememberIllustration(activeRoleId, path);
                    }
                  }}
                >
                  <img src={toFileUrl(path)} alt="illustration thumb" />
                </button>
              ))}
            </div>
          ) : null}
          {roleForm.avatarSource ? <div className="asset-preview">Avatar: {roleForm.avatarSource}</div> : null}
          {roleForm.illustrationSources.length ? (
            <div className="asset-preview">
              Illustrations:
              <ul>
                {roleForm.illustrationSources.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          <div className="editor-actions">
            <button className="ghost-btn" type="button" onClick={onResetRoleForm} disabled={!roleFormDirty}>
              Reset
            </button>
            <button data-testid="save-role-button" className="primary-btn" type="button" onClick={onSaveRole} disabled={savingRole || !activeRoleId || !roleFormDirty || !bridgeReady}>
              {savingRole ? "Saving..." : "Save Role"}
            </button>
          </div>
        </div>
      ) : (
        <div className="empty-card">Select a role to edit its prompt and local artwork.</div>
      )}
    </section>
  );
}
