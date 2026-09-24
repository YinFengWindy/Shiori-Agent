import { ArrowCounterClockwise, ChatCircleDots, FloppyDisk } from "@phosphor-icons/react";
import { SpinnerIcon } from "../shared/icons";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../shared/styles";
import type { RoleDetailSaveState } from "./roleDetailSaveState";

type RoleDetailActionsProps = {
  canGoToChat: boolean;
  saveState: RoleDetailSaveState;
  onGoToChat: () => void;
  onReset: () => void;
  onSave: () => void;
};

/** The role header's labeled actions: 去聊天, 重置 and the primary 保存. */
export function RoleDetailActions({ canGoToChat, saveState, onGoToChat, onReset, onSave }: RoleDetailActionsProps) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <button
        className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}
        data-testid="role-detail-go-to-chat"
        type="button"
        onClick={onGoToChat}
        disabled={!canGoToChat}
      >
        <ChatCircleDots className="h-4 w-4" weight="duotone" aria-hidden="true" />
        去聊天
      </button>
      <button
        className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}
        data-testid="reset-role-button"
        type="button"
        onClick={onReset}
        disabled={!saveState.canReset}
      >
        <ArrowCounterClockwise className="h-4 w-4" aria-hidden="true" />
        重置
      </button>
      <button
        className={cx(primaryButtonSurfaceClass, compactButtonSizeClass, "min-w-[88px]")}
        data-testid="save-role-button"
        data-saving={saveState.saving ? "true" : "false"}
        type="button"
        onClick={onSave}
        disabled={!saveState.canSave}
        aria-busy={saveState.saving}
      >
        {saveState.saving
          ? <SpinnerIcon className="h-4 w-4 animate-spin stroke-current" />
          : <FloppyDisk className="h-4 w-4" aria-hidden="true" />}
        {saveState.saveLabel}
      </button>
    </div>
  );
}
