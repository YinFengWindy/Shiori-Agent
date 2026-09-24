import { useLayoutEffect, useRef, useState } from "react";
import { BackIcon, ResetIcon, SaveIcon } from "../shared/icons";
import { cx, iconButtonClass } from "../shared/styles";
import { Magnet } from "../shared/ui/reactBits/Magnet";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";
import { captureRoleDetailScrollTop, restoreRoleDetailScrollTop } from "./roleDetailScrollState";
import { RoleDetailTabs, type RoleDetailTabId } from "./RoleDetailTabs";
import { RoleProfilePanel } from "./RoleProfilePanel";
import { RoleKnowledgePanel } from "./RoleKnowledgePanel";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";

type RoleDetailPageProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  chatBackgroundUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onBackToList: () => void;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders the focused role archive editor with a shared draft across task tabs. */
export function RoleDetailPage({
  activeRole,
  activeRoleId,
  bridgeReady,
  previewAvatar,
  roleForm,
  roleFormDirty,
  savingRole,
  onBackToList,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  const pageRef = useRef<HTMLElement | null>(null);
  const pendingScrollTopRef = useRef<number | null>(null);
  const [activeTab, setActiveTab] = useState<RoleDetailTabId>("profile");
  // The first tab appears with the page; only later switches animate in.
  const [tabSwitched, setTabSwitched] = useState(false);
  const floatingActionClass = cx(iconButtonClass, "shadow-soft disabled:cursor-not-allowed disabled:bg-surface-soft disabled:text-ink-faint disabled:opacity-100 disabled:shadow-none");

  useLayoutEffect(() => {
    pendingScrollTopRef.current = restoreRoleDetailScrollTop(pageRef.current, pendingScrollTopRef.current);
  }, [roleForm]);

  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    pendingScrollTopRef.current = captureRoleDetailScrollTop(pageRef.current);
    onUpdateRoleForm(next);
  }

  const content = activeTab === "profile" ? (
    <RoleProfilePanel activeRole={activeRole} previewAvatar={previewAvatar} roleForm={roleForm} onOpenAssetsPage={onOpenAssetsPage} onUpdate={updateRoleForm} />
  ) : activeTab === "knowledge" ? (
    <RoleKnowledgePanel roleForm={roleForm} onUpdate={updateRoleForm} />
  ) : activeTab === "capabilities" ? (
    <RoleCapabilitiesPanel activeRole={activeRole} bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={updateRoleForm} />
  ) : (
    <div className="grid gap-6">
      <RoleChannelBindingsPanel activeRoleId={activeRoleId} bindings={roleForm.channelBindings ?? []} onUpdate={updateRoleForm} />
      <RoleProactiveSettingsPanel bindings={roleForm.channelBindings ?? []} roleForm={roleForm} onUpdate={updateRoleForm} />
    </div>
  );

  return (
    <section ref={pageRef} className="role-detail-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-gradient-app bg-fixed" data-testid="role-detail-page" data-has-featured-image="false">
      <div className="relative mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-5 pb-8 pt-6 sm:px-8">
        <div data-testid="role-detail-info-card">
          <div className="mb-6 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-line-soft pb-4">
            <button className={cx(floatingActionClass, "motion-safe:hover:-translate-x-0.5")} data-testid="role-detail-back-button" type="button" onClick={onBackToList} aria-label="返回角色列表"><BackIcon className="h-5 w-5 fill-current" /></button>
            <RoleDetailTabs activeTab={activeTab} onChange={(tab) => { setTabSwitched(true); setActiveTab(tab); }} />
            <div className="flex items-center gap-2">
              <button className={floatingActionClass} type="button" onClick={onResetRoleForm} disabled={!roleFormDirty} aria-label="重置角色表单"><ResetIcon className="h-[18px] w-[18px] fill-current" /></button>
              <Magnet disabled={savingRole || !roleFormDirty || !bridgeReady} padding={52} strength={9}><button className={cx(floatingActionClass, "border-white/70 bg-gradient-accent hover:shadow-panel")} data-testid="save-role-button" type="button" onClick={onSaveRole} disabled={savingRole || !roleFormDirty || !bridgeReady} aria-label={savingRole ? "正在保存角色" : "保存角色"}><SaveIcon className="h-5 w-5 fill-current" /></button></Magnet>
            </div>
          </div>
          {/* Enter-only: the outgoing tab leaves at once so switching never waits on an exit. */}
          <div key={activeTab} className={cx(tabSwitched && "motion-tab-enter")}>
            {content}
          </div>
        </div>
      </div>
    </section>
  );
}
