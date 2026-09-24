import { nameViewTransitionElement, runViewTransition } from "../shared/viewTransition";

/**
 * Card ↔ detail shared-element transition for the role workspace. The card
 * (`data-role-card`) and the detail header (`data-role-detail-header`) mark
 * the parts that morph with `data-vt-part`: the portrait, the avatar, the
 * name and the intro. The page itself (`data-role-page`) fades out and the
 * incoming page rises in; see the `role-*` rules in styles.css.
 */
const pagePart = "role-page";

function roleCard(roleId: string): Element | null {
  return document.querySelector(`[data-role-card="${CSS.escape(roleId)}"]`);
}

function detailHeader(): Element | null {
  return document.querySelector("[data-role-detail-header]");
}

/** Names the page and every marked part inside `scope` (`role-portrait`, `role-name`, …). */
function nameRoleParts(scope: Element | null): void {
  nameViewTransitionElement(document.querySelector("[data-role-page]"), pagePart);
  scope?.querySelectorAll("[data-vt-part]").forEach((element) => {
    nameViewTransitionElement(element, `role-${element.getAttribute("data-vt-part")}`);
  });
}

/** Opens a role's detail from its card: the card's portrait, name and intro morph into the header. */
export function openRoleDetailWithTransition(roleId: string, update: () => void): Promise<void> {
  return runViewTransition({
    update,
    nameOld: () => nameRoleParts(roleCard(roleId)),
    nameNew: () => nameRoleParts(detailHeader()),
  });
}

/**
 * Returns to the grid, morphing the header back into the role's own card.
 * From anywhere without the header (e.g. the create page) it is a plain page
 * swap, so no card part fades in on its own.
 */
export function closeRoleDetailWithTransition(roleId: string, update: () => void): Promise<void> {
  let fromHeader = false;
  return runViewTransition({
    update,
    nameOld: () => {
      const header = detailHeader();
      fromHeader = header !== null;
      nameRoleParts(header);
    },
    nameNew: () => nameRoleParts(fromHeader ? roleCard(roleId) : null),
  });
}
