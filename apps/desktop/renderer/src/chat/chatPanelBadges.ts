import type { ChatSidebarMode } from "./ChatRightSidebar";

/**
 * "Something new here" dots for the chat role panel. New content never
 * opens the panel or switches its segment any more; it marks the segment
 * instead, and the closed panel's toggle shows a dot while any mark is up.
 */
export type ChatPanelBadges = {
  status: boolean;
  images: boolean;
};

/** What the user currently sees: whether the panel is open and on which segment. */
export type ChatPanelView = {
  open: boolean;
  mode: ChatSidebarMode;
};

export const emptyChatPanelBadges: ChatPanelBadges = { status: false, images: false };

function isViewing(view: ChatPanelView, mode: ChatSidebarMode): boolean {
  return view.open && view.mode === mode;
}

/**
 * Marks segments that received new content the user is not looking at.
 * `newImage`: the chat image count grew. `newThought`: the role's current
 * thought changed to a non-empty value. Returns the same object when nothing changes.
 */
export function markChatPanelUpdates(
  badges: ChatPanelBadges,
  update: { newImage: boolean; newThought: boolean },
  view: ChatPanelView,
): ChatPanelBadges {
  const images = badges.images || (update.newImage && !isViewing(view, "images"));
  const status = badges.status || (update.newThought && !isViewing(view, "status"));
  return images === badges.images && status === badges.status ? badges : { images, status };
}

/** Clears the mark on the segment the user is now looking at. Returns the same object when nothing changes. */
export function clearViewedChatPanelBadge(badges: ChatPanelBadges, view: ChatPanelView): ChatPanelBadges {
  if (!view.open) return badges;
  if (view.mode === "images" && badges.images) return { ...badges, images: false };
  if (view.mode === "status" && badges.status) return { ...badges, status: false };
  return badges;
}

/** Whether the panel toggle should carry a dot: only while the panel is closed and something is unseen. */
export function shouldBadgeChatPanelToggle(badges: ChatPanelBadges, open: boolean): boolean {
  return !open && (badges.images || badges.status);
}
