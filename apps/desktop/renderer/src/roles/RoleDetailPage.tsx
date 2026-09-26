import { useLayoutEffect, useRef, useState } from "react";
import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";
import { resolveRoleCardCover } from "./roleCardState";
import { captureRoleDetailScrollTop, restoreRoleDetailScrollTop } from "./roleDetailScrollState";
import { RoleDeliveryPanels } from "./RoleDeliveryPanels";
import { RoleDetailHeader } from "./RoleDetailHeader";
import { selectRoleDetailSaveState } from "./roleDetailSaveState";
import type { RoleDetailTabId } from "./RoleDetailTabs";
import { RoleDetailToolbar } from "./RoleDetailToolbar";
import { RoleMemoryPanel } from "./RoleMemoryPanel";
import { RoleProfilePanel } from "./RoleProfilePanel";
import { RoleAccountsPanel } from "../accounts/RoleAccountsPanel";

type RoleDetailPageProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  /** The role's current mood (its chat's, else its default); empty when it has none. */
  currentMood: string;
  /** The illustration bound to that mood, as a URL; empty when there is none. */
  moodIllustrationUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onBackToList: () => void;
  /** Switches to the chat with this role. */
  onGoToChat: () => void;
  onOpenAssetsPage: () => void;
  /** Opens 设置 › 插件, on the given plugin's own settings tab when there is one. */
  onOpenPluginSettings: (pluginId: string | null) => void;
  /** The role's model binding changed outside the draft; the app's role snapshot must catch up. */
  onRoleModelChanged: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders the focused role archive editor: a character header over a shared draft across task tabs. */
export function RoleDetailPage({
  activeRole,
  activeRoleId,
  bridgeReady,
  previewAvatar,
  currentMood,
  moodIllustrationUrl,
  roleForm,
  roleFormDirty,
  savingRole,
  onBackToList,
  onGoToChat,
  onOpenAssetsPage,
  onOpenPluginSettings,
  onRoleModelChanged,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  const pageRef = useRef<HTMLElement | null>(null);
  const pendingScrollTopRef = useRef<number | null>(null);
  const [activeTab, setActiveTab] = useState<RoleDetailTabId>("profile");
  // The first tab appears with the page; only later switches animate in.
  const [tabSwitched, setTabSwitched] = useState(false);
  const saveState = selectRoleDetailSaveState({ dirty: roleFormDirty, saving: savingRole, bridgeReady });
  const cover = activeRole ? resolveRoleCardCover(activeRole) : "";
  const portraitUrl = moodIllustrationUrl || (cover ? toFileUrl(cover) : "");

  useLayoutEffect(() => {
    pendingScrollTopRef.current = restoreRoleDetailScrollTop(pageRef.current, pendingScrollTopRef.current);
  }, [roleForm]);

  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    pendingScrollTopRef.current = captureRoleDetailScrollTop(pageRef.current);
    onUpdateRoleForm(next);
  }

  const content = activeTab === "profile" ? (
    <div className="grid gap-7">
      <RoleProfilePanel
        roleId={activeRole?.id ?? ""}
        roleRevision={activeRole?.updated_at ?? ""}
        bridgeReady={bridgeReady}
        roleForm={roleForm}
        onUpdate={updateRoleForm}
        onModelChanged={onRoleModelChanged}
      />
      {activeRoleId ? <RoleAccountsPanel roleId={activeRoleId} onOpenPluginSettings={onOpenPluginSettings} /> : null}
    </div>
  ) : activeTab === "memory" ? (
    <RoleMemoryPanel roleId={activeRoleId} bridgeReady={bridgeReady} />
  ) : activeTab === "capabilities" ? (
    <RoleCapabilitiesPanel activeRole={activeRole} bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={updateRoleForm} />
  ) : (
    <RoleDeliveryPanels roleForm={roleForm} onUpdate={updateRoleForm} />
  );

  return (
    <section ref={pageRef} className="role-detail-page scrollbar-stable relative h-full overflow-y-auto bg-gradient-app bg-fixed" data-testid="role-detail-page" data-role-page="">
      <div className="relative mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-5 pb-10 pt-6 sm:px-8" data-testid="role-detail-info-card">
        <RoleDetailHeader
          activeRole={activeRole}
          previewAvatar={previewAvatar}
          portraitUrl={portraitUrl}
          currentMood={currentMood}
          roleForm={roleForm}
          onOpenAssetsPage={onOpenAssetsPage}
          onUpdate={updateRoleForm}
        />
        <RoleDetailToolbar
          activeTab={activeTab}
          canGoToChat={bridgeReady && Boolean(activeRole)}
          saveState={saveState}
          onBack={onBackToList}
          onChangeTab={(tab) => { setTabSwitched(true); setActiveTab(tab); }}
          onGoToChat={onGoToChat}
          onReset={onResetRoleForm}
          onSave={onSaveRole}
        />
        {/* Enter-only: the outgoing tab leaves at once so switching never waits on an exit. */}
        <div key={activeTab} className={cx(tabSwitched && "motion-tab-enter")}>
          {content}
        </div>
      </div>
    </section>
  );
}
