import { BackIcon } from "../shared/icons";
import { cx, iconButtonClass } from "@yinfengwindy/shiori-sdk";
import { RoleDetailActions } from "./RoleDetailActions";
import type { RoleDetailSaveState } from "./roleDetailSaveState";
import { RoleDetailTabs, roleDetailTabEditsDraft, type RoleDetailTabId } from "./RoleDetailTabs";
import { roleEditorToolbarClass } from "./roleEditorStyles";

type RoleDetailToolbarProps = {
  activeTab: RoleDetailTabId;
  canGoToChat: boolean;
  saveState: RoleDetailSaveState;
  onBack: () => void;
  onChangeTab: (tab: RoleDetailTabId) => void;
  onGoToChat: () => void;
  onReset: () => void;
  onSave: () => void;
};

/**
 * The role detail page's sticky bar: back, the tabs, and 去聊天 / 重置 / 保存.
 * It sticks to the top of the scrolling page so 保存 is always one click away,
 * however far down a long setting the user has scrolled.
 */
export function RoleDetailToolbar({ activeTab, canGoToChat, saveState, onBack, onChangeTab, onGoToChat, onReset, onSave }: RoleDetailToolbarProps) {
  return (
    <div
      className={roleEditorToolbarClass}
      data-testid="role-detail-toolbar"
    >
      <button className={cx(iconButtonClass, "self-center")} data-testid="role-detail-back-button" type="button" onClick={onBack} aria-label="返回角色列表">
        <BackIcon className="h-5 w-5 fill-current" />
      </button>
      <div className="flex min-w-0 flex-1 items-end">
        <RoleDetailTabs activeTab={activeTab} onChange={onChangeTab} />
      </div>
      <div className="self-center">
        <RoleDetailActions canGoToChat={canGoToChat} showEditorActions={roleDetailTabEditsDraft(activeTab)} saveState={saveState} onGoToChat={onGoToChat} onReset={onReset} onSave={onSave} />
      </div>
    </div>
  );
}
