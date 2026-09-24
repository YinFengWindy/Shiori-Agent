import { ChatCircleDots, DotsThree, PencilSimple, Trash } from "@phosphor-icons/react";
import { toFileUrl } from "../shared/format";
import { SpinnerIcon } from "../shared/icons";
import { compactPressableClass, cx } from "../shared/styles";
import { ActionMenu } from "../shared/ui/ActionMenu";
import type { PendingRoleCardAction, RoleRecord } from "../shared/types";
import { roleCardPendingLabels, selectRoleCardView } from "./roleCardState";
import { RolePortraitPlaceholder } from "./RolePortraitPlaceholder";

type RoleCardProps = {
  role: RoleRecord;
  active: boolean;
  bridgeReady: boolean;
  pendingCardAction: PendingRoleCardAction;
  onOpen: () => void;
  onGoToChat: () => void;
  onDelete: () => void;
};

/**
 * One role in the management grid. The card is a plain container: the whole
 * face is one stretched 「打开」 button, and the secondary actions live in the
 * corner overflow menu, so no button ever nests inside another.
 */
export function RoleCard({ role, active, bridgeReady, pendingCardAction, onOpen, onGoToChat, onDelete }: RoleCardProps) {
  const view = selectRoleCardView(role, pendingCardAction);
  const blocked = !bridgeReady || view.pending !== null;

  return (
    <article
      className={cx(
        "group relative isolate aspect-[4/5] overflow-hidden rounded-lg border bg-surface shadow-soft transition-[transform,box-shadow,border-color] duration-base ease-out-soft hover:shadow-pop focus-within:shadow-pop motion-safe:hover:-translate-y-0.5",
        active ? "border-line-accent" : "border-line-soft",
      )}
      data-testid={`role-management-card-${role.id}`}
      data-has-portrait={view.coverPath ? "true" : "false"}
    >
      {view.coverPath ? (
        <>
          <img
            className="absolute inset-0 h-full w-full object-cover object-top transition-transform duration-panel ease-out-soft motion-safe:group-hover:scale-[1.03]"
            src={toFileUrl(view.coverPath)}
            alt=""
          />
          {/* Warm-white scrim so ink text stays readable over any portrait. */}
          <div className="absolute inset-x-0 bottom-0 h-3/5 bg-gradient-to-t from-white/95 via-white/75 to-transparent" aria-hidden="true" />
        </>
      ) : (
        <RolePortraitPlaceholder avatarPath={view.avatarPath} initial={view.initial} name={role.name} />
      )}
      <button
        className="absolute inset-0 z-[1] rounded-lg disabled:cursor-default"
        data-testid={`role-card-open-${role.id}`}
        type="button"
        disabled={blocked}
        onClick={onOpen}
        aria-label={`打开 ${role.name}`}
      />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] grid gap-1 p-4">
        <h3 className="m-0 truncate font-display text-title text-ink">{role.name}</h3>
        {view.description ? <p className="m-0 line-clamp-2 text-body-sm leading-5 text-ink-secondary">{view.description}</p> : null}
      </div>
      <div className="absolute right-3 top-3 z-[3]">
        <ActionMenu
          label={`${role.name} 的更多操作`}
          data-testid={`role-card-more-${role.id}`}
          disabled={blocked}
          triggerClassName={cx(
            compactPressableClass,
            "surface-glass-strong grid h-8 w-8 place-items-center rounded-full text-ink-secondary hover:text-ink disabled:opacity-50",
          )}
          items={[
            { id: "chat", label: "去聊天", icon: <ChatCircleDots className="h-4 w-4" />, onSelect: onGoToChat },
            { id: "edit", label: "编辑", icon: <PencilSimple className="h-4 w-4" />, onSelect: onOpen },
            { id: "delete", label: "删除角色", icon: <Trash className="h-4 w-4" />, danger: true, separated: true, onSelect: onDelete },
          ]}
        >
          <DotsThree className="h-5 w-5" weight="bold" aria-hidden="true" />
        </ActionMenu>
      </div>
      {view.pending ? (
        <div className="absolute inset-0 z-[4] grid place-items-center bg-white/40 backdrop-blur-sm">
          <span
            className="grid h-14 w-14 place-items-center rounded-full bg-surface text-accent-text shadow-panel"
            data-testid={`role-card-spinner-${role.id}`}
            role="status"
            aria-label={roleCardPendingLabels[view.pending]}
          >
            <SpinnerIcon className="h-6 w-6 animate-spin stroke-current" />
          </span>
        </div>
      ) : null}
    </article>
  );
}
