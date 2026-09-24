type RoleDetailSaveInput = {
  dirty: boolean;
  saving: boolean;
  bridgeReady: boolean;
};

/** What the role header's 保存 / 重置 buttons show and allow. */
export type RoleDetailSaveState = {
  canSave: boolean;
  canReset: boolean;
  saveLabel: string;
  saving: boolean;
};

/**
 * Save is offered only for a changed draft while the bridge is up and no save
 * is running; reset only for a changed draft that is not being saved (a reset
 * mid-save would be overwritten by the save's own refresh).
 */
export function selectRoleDetailSaveState({ dirty, saving, bridgeReady }: RoleDetailSaveInput): RoleDetailSaveState {
  return {
    canSave: dirty && !saving && bridgeReady,
    canReset: dirty && !saving,
    saveLabel: saving ? "保存中…" : "保存",
    saving,
  };
}
