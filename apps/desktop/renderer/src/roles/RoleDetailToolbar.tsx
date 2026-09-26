import { BackIcon } from "../shared/icons";
import { cx, iconButtonClass } from "../shared/styles";
import { RoleDetailActions } from "./RoleDetailActions";
import type { RoleDetailSaveState } from "./roleDetailSaveState";
import { RoleDetailTabs, type RoleDetailTabId } from "./RoleDetailTabs";

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
      className="sticky top-0 z-20 -mx-5 mb-7 mt-5 flex min-h-[56px] items-stretch gap-4 border-b border-line-soft bg-white/80 px-5 backdrop-blur-md sm:-mx-8 sm:px-8"
      data-testid="role-detail-toolbar"
    >
      <button className={cx(iconButtonClass, "self-center")} data-testid="role-detail-back-button" type="button" onClick={onBack} aria-label="返回角色列表">
        <BackIcon className="h-5 w-5 fill-current" />
      </button>
      <div className="flex min-w-0 flex-1 items-end">
        <RoleDetailTabs activeTab={activeTab} onChange={onChangeTab} />
      </div>
      <div className="self-center">
        <RoleDetailActions canGoToChat={canGoToChat} showEditorActions={activeTab !== "memory"} saveState={saveState} onGoToChat={onGoToChat} onReset={onReset} onSave={onSave} />
      </div>
    </div>
  );
}
