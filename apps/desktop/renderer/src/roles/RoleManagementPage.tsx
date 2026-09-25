import { Plus, UploadSimple } from "@phosphor-icons/react";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { MascotEmptyState } from "../shared/mascot/MascotSpeech";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "../shared/styles";
import { PetalIcon, RibbonIcon, SparkleIcon } from "../shared/ui/icons";
import type { PendingRoleCardAction, RoleRecord } from "../shared/types";
import { RoleCard } from "./RoleCard";

type RoleManagementPageProps = {
  activeRoleId: string;
  bridgeReady: boolean;
  /** Whether a role card import can start (bridge up, no import already running). */
  canImportRoleCard: boolean;
  pendingCardAction: PendingRoleCardAction;
  roles: RoleRecord[];
  onOpenRoleDetail: (roleId: string) => void;
  onGoToChat: (roleId: string) => void;
  onDeleteRole: (roleId: string) => void;
  onCreateRole: () => void;
  onImportRoleCard: () => void;
};

const emptyActionClass = "inline-flex h-11 items-center gap-2 px-5 text-body font-medium";

/** Renders the first-level role management screen with the full role list. */
export function RoleManagementPage({
  activeRoleId,
  bridgeReady,
  canImportRoleCard,
  pendingCardAction,
  roles,
  onOpenRoleDetail,
  onGoToChat,
  onDeleteRole,
  onCreateRole,
  onImportRoleCard,
}: RoleManagementPageProps) {
  const mascotEnabled = useMascotEnabled();
  const emptyActions = (
    <>
      <button className={cx(primaryButtonSurfaceClass, emptyActionClass)} type="button" disabled={!bridgeReady} onClick={onCreateRole}>
        <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
        新建角色
      </button>
      <button className={cx(ghostButtonSurfaceClass, emptyActionClass)} type="button" disabled={!canImportRoleCard} onClick={onImportRoleCard}>
        <UploadSimple className="h-4 w-4" aria-hidden="true" />
        导入角色卡
      </button>
    </>
  );
  return (
    <section
      className="role-management-page scrollbar-stable h-full overflow-y-auto bg-gradient-app bg-fixed"
      data-testid="role-management-page"
      data-role-page=""
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1280px] flex-col px-8 pb-10 pt-8">
        {roles.length ? (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(236px,1fr))] gap-5">
            {roles.map((role) => (
              <RoleCard
                key={role.id}
                role={role}
                active={role.id === activeRoleId}
                bridgeReady={bridgeReady}
                pendingCardAction={pendingCardAction}
                onOpen={() => onOpenRoleDetail(role.id)}
                onGoToChat={() => onGoToChat(role.id)}
                onDelete={() => onDeleteRole(role.id)}
              />
            ))}
          </div>
        ) : mascotEnabled ? (
          // 吟风 fronts the empty grid (an owner-approved line, #362 stage 10).
          <div className="grid flex-1 place-items-center">
            <MascotEmptyState line={emptyStateLines.noRoles} layout="side" testId="role-management-empty">
              {emptyActions}
            </MascotEmptyState>
          </div>
        ) : (
          <div className="grid flex-1 place-items-center" data-testid="role-management-empty">
            <div className="grid justify-items-center gap-7">
              <div className="relative grid h-32 w-32 place-items-center rounded-full bg-gradient-accent-soft shadow-soft" aria-hidden="true">
                <SparkleIcon className="h-14 w-14 text-accent-text" />
                <PetalIcon className="absolute -right-1 top-3 h-6 w-6 rotate-12 text-accent-text opacity-60" />
                <RibbonIcon className="absolute -left-2 bottom-5 h-7 w-7 -rotate-12 text-lavender-text opacity-60" />
              </div>
              <div className="flex flex-wrap justify-center gap-3">{emptyActions}</div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
