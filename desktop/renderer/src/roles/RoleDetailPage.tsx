import { AnimatePresence, motion } from "motion/react";
import { useLayoutEffect, useRef, useState } from "react";
import { BackIcon, ResetIcon, SaveIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import { Magnet } from "../shared/ui/reactBits/Magnet";
import { SpotlightCard } from "../shared/ui/reactBits/SpotlightCard";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";
import { captureRoleDetailScrollTop, restoreRoleDetailScrollTop } from "./roleDetailScrollState";
import { RoleDetailTabs, type RoleDetailTabId } from "./RoleDetailTabs";
import { RoleProfilePanel } from "./RoleProfilePanel";
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
  chatBackgroundUrl,
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
  const floatingActionClass = "grid h-10 w-10 place-items-center rounded-full border border-white/35 bg-white/88 text-[#36231b] shadow-[0_8px_24px_rgba(15,23,42,0.16)] transition hover:bg-white disabled:cursor-default disabled:border-white/20 disabled:bg-white/45 disabled:text-white/55 disabled:shadow-none";

  useLayoutEffect(() => {
    pendingScrollTopRef.current = restoreRoleDetailScrollTop(pageRef.current, pendingScrollTopRef.current);
  }, [roleForm]);

  function updateRoleForm(next: React.SetStateAction<RoleFormState>): void {
    pendingScrollTopRef.current = captureRoleDetailScrollTop(pageRef.current);
    onUpdateRoleForm(next);
  }

  const content = activeTab === "profile" ? (
    <RoleProfilePanel activeRole={activeRole} previewAvatar={previewAvatar} roleForm={roleForm} onOpenAssetsPage={onOpenAssetsPage} onUpdate={updateRoleForm} />
  ) : activeTab === "capabilities" ? (
    <RoleCapabilitiesPanel activeRole={activeRole} bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={updateRoleForm} />
  ) : (
    <div className="grid gap-4">
      <RoleChannelBindingsPanel activeRoleId={activeRoleId} bindings={roleForm.channelBindings ?? []} onUpdate={updateRoleForm} />
      <RoleProactiveSettingsPanel bindings={roleForm.channelBindings ?? []} roleForm={roleForm} onUpdate={updateRoleForm} />
    </div>
  );

  return (
    <section ref={pageRef} className="role-detail-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-[#17110f]" data-testid="role-detail-page" data-has-featured-image={chatBackgroundUrl ? "true" : "false"}>
      {chatBackgroundUrl ? <div className="absolute inset-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: `url("${chatBackgroundUrl}")` }} data-testid="role-illustration-hero" /> : <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#f8d4bf_0%,#d89270_44%,#6d473e_100%)]" data-testid="role-illustration-hero" />}
      <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,245,238,0.12),rgba(255,245,238,0.02)_42%,rgba(255,245,238,0.16))]" />
      <div className="relative mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-5 pb-8 pt-6 sm:px-8">
        <SpotlightCard className="rounded-[18px] border border-white/80 bg-[rgba(255,252,249,0.94)] p-4 shadow-[0_18px_48px_rgba(70,38,25,0.2)] backdrop-blur-md sm:p-7" spotlightColor="rgba(237, 155, 111, 0.18)">
          <div data-testid="role-detail-info-card">
            <div className="mb-6 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-[#eaded6] pb-4">
              <button className={cx(floatingActionClass, "hover:-translate-x-0.5")} data-testid="role-detail-back-button" type="button" onClick={onBackToList} aria-label="返回角色列表"><BackIcon className="h-5 w-5 fill-current" /></button>
              <RoleDetailTabs activeTab={activeTab} onChange={setActiveTab} />
              <div className="flex items-center gap-2">
                <button className={floatingActionClass} type="button" onClick={onResetRoleForm} disabled={!roleFormDirty} aria-label="重置角色表单"><ResetIcon className="h-[18px] w-[18px] fill-current" /></button>
                <Magnet disabled={savingRole || !roleFormDirty || !bridgeReady} padding={52} strength={9}><button className={cx(floatingActionClass, "bg-[#fff7f0] hover:shadow-[0_10px_28px_rgba(255,217,184,0.32)]")} data-testid="save-role-button" type="button" onClick={onSaveRole} disabled={savingRole || !roleFormDirty || !bridgeReady} aria-label={savingRole ? "正在保存角色" : "保存角色"}><SaveIcon className="h-5 w-5 fill-current" /></button></Magnet>
              </div>
            </div>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={activeTab} initial={{ opacity: 0, y: 10, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} exit={{ opacity: 0, y: -6, filter: "blur(3px)" }} transition={{ duration: 0.2, ease: "easeOut" }}>
                {content}
              </motion.div>
            </AnimatePresence>
          </div>
        </SpotlightCard>
      </div>
    </section>
  );
}
