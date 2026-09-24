import { nameViewTransitionElement, runViewTransition } from "../shared/viewTransition";

/**
 * Switching roles from the chat list as a shared-element view transition:
 * the clicked row's avatar and name (`[data-chat-role-row] [data-vt-part]`)
 * morph into the chat header while the old header's pair shrinks away, the
 * background portrait (`[data-chat-backdrop]`) settles in from a slight zoom
 * over the old one, and the conversation (`[data-chat-conversation]`) fades
 * out and rises back in. The header bar is named too so it stays above the
 * backdrop layer. Timing and clipping: the `chat-*` rules in styles.css.
 *
 * Only the role switch is animated here; a new mood portrait or background
 * for the same role crossfades in `CrossfadeLayers`, which swaps outright on
 * a role change (its `resetKey`).
 */

function part(scope: Element | null, name: "avatar" | "name"): Element | null {
  return scope?.querySelector(`[data-vt-part="${name}"]`) ?? null;
}

/** Names the chat surface's layers so none of them paints over another mid-transition. */
function nameStage(): Element | null {
  const header = document.querySelector("[data-chat-header]");
  nameViewTransitionElement(document.querySelector("[data-chat-backdrop]"), "chat-backdrop");
  nameViewTransitionElement(header, "chat-header");
  nameViewTransitionElement(document.querySelector("[data-chat-conversation]"), "chat-conversation");
  return header;
}

function listRow(roleId: string): Element | null {
  return Array.from(document.querySelectorAll("[data-chat-role-row]")).find((row) => row.getAttribute("data-chat-role-row") === roleId) ?? null;
}

/** Runs `update` (which opens `roleId`) as the chat role-switch transition. */
export function switchChatRoleWithTransition(roleId: string, update: () => void): Promise<void> {
  return runViewTransition({
    update,
    nameOld: () => {
      const header = nameStage();
      nameViewTransitionElement(part(header, "avatar"), "chat-role-avatar-old");
      nameViewTransitionElement(part(header, "name"), "chat-role-name-old");
      const row = listRow(roleId);
      nameViewTransitionElement(part(row, "avatar"), "chat-role-avatar");
      nameViewTransitionElement(part(row, "name"), "chat-role-name");
    },
    nameNew: () => {
      const header = nameStage();
      nameViewTransitionElement(part(header, "avatar"), "chat-role-avatar");
      nameViewTransitionElement(part(header, "name"), "chat-role-name");
    },
  });
}

type OpenChatRoleArgs = {
  roleId: string;
  /** The role open right now. */
  activeRoleId: string;
  /** Whether the chat surface is on screen (the list also shows beside plugin pages). */
  chatShown: boolean;
  /** Opens the role. */
  open: () => void;
};

/**
 * Opens a role picked in the chat list: animated as a role switch while the
 * chat is on screen and the role actually changes, directly otherwise
 * (re-clicking the open role, or picking from beside a plugin page).
 */
export function openChatRole({ roleId, activeRoleId, chatShown, open }: OpenChatRoleArgs): Promise<void> {
  if (!chatShown || roleId === activeRoleId) {
    open();
    return Promise.resolve();
  }
  return switchChatRoleWithTransition(roleId, open);
}
