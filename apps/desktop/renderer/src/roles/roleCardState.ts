import type { PendingRoleCardAction, RoleRecord } from "../shared/types";
import { resolveMoodIllustration } from "./roleMoodSelectors";

/** What one role card in the management grid shows. */
export type RoleCardView = {
  /** Local path of the portrait on the card face; empty when the role has none. */
  coverPath: string;
  avatarPath: string;
  /** First character of the name, shown when there is no avatar. */
  initial: string;
  /** Trimmed one-line intro; empty when the role has none (the card then shows only the name). */
  description: string;
  /** An in-flight create/delete for this card; it blocks opening and actions. */
  pending: "create" | "delete" | null;
};

/**
 * The card's portrait: the illustration bound to the role's default mood
 * (the same one the chat shows before any mood is set), else its chat
 * background. A role with neither gets the designed placeholder instead.
 */
export function resolveRoleCardCover(role: RoleRecord): string {
  const moodIllustration = resolveMoodIllustration({
    activeSession: null,
    detailRole: role,
    roleForm: { defaultMood: "", moodIllustrationBindings: {} },
    useRoleForm: false,
  });
  // A binding that no longer resolves to a library file comes back as its raw relative path; skip it.
  const resolvedMood = moodIllustration && role.illustrations_abs.includes(moodIllustration) ? moodIllustration : "";
  return resolvedMood || role.chat_background_abs || "";
}

/** Builds the card view for one role, including its pending create/delete state. */
export function selectRoleCardView(role: RoleRecord, pendingCardAction: PendingRoleCardAction): RoleCardView {
  return {
    coverPath: resolveRoleCardCover(role),
    avatarPath: role.avatar_abs ?? "",
    initial: role.name.trim().slice(0, 1).toUpperCase() || "?",
    description: role.description.trim(),
    pending: pendingCardAction?.roleId === role.id ? pendingCardAction.action : null,
  };
}

/** Accessible label of a card's pending spinner. */
export const roleCardPendingLabels: Record<NonNullable<RoleCardView["pending"]>, string> = {
  create: "正在创建角色",
  delete: "正在删除角色",
};
