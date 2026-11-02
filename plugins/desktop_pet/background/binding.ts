import type { DesktopPetActionState, DesktopPetBinding } from "./types";

const actionStates = new Set<string>([
  "idle",
  "running-right",
  "running-left",
  "waving",
  "jumping",
]);

/**
 * Turns a `desktop_pet.binding.get` response into a binding, or `null`.
 *
 * `null` covers every "nothing to show" case in one answer — no pet-enabled
 * role, no selected package, a package whose spritesheet the host would not
 * grant — because the only caller does the same thing for all of them: hide
 * the pet. Before #181-C this parsing sat in `main.ts` and read the core
 * `roles.list` payload directly; it now reads the plugin's own RPC, which is
 * the only bridge namespace background code can reach.
 *
 * `resolveAssetUrl` is `ctx.assets.url`. A granted path becomes an opaque
 * `shiori-asset://` URL; an ungranted one is `null`, and is treated as no
 * binding at all rather than as a pet with a broken image.
 */
export function readDesktopPetBinding(
  value: unknown,
  resolveAssetUrl: (path: string) => string | null,
): DesktopPetBinding | null {
  if (!value || typeof value !== "object") return null;
  const binding = (value as { binding?: unknown }).binding;
  if (!binding || typeof binding !== "object") return null;
  const source = binding as { role_id?: unknown; package?: unknown; actions?: unknown };
  if (typeof source.role_id !== "string" || !source.role_id) return null;
  if (!source.package || typeof source.package !== "object") return null;
  const packageValue = source.package as {
    id?: unknown;
    display_name?: unknown;
    spritesheet_abs?: unknown;
  };
  if (typeof packageValue.id !== "string" || !packageValue.id) return null;
  if (typeof packageValue.display_name !== "string") return null;
  if (typeof packageValue.spritesheet_abs !== "string") return null;
  const spritesheetUrl = resolveAssetUrl(packageValue.spritesheet_abs);
  if (!spritesheetUrl) return null;
  return {
    roleId: source.role_id,
    package: {
      id: packageValue.id,
      displayName: packageValue.display_name,
      spritesheetUrl,
    },
    actions: readActions(source.actions),
  };
}

/**
 * Keeps only action states the sprite atlas can actually play.
 *
 * The backend validates these on package import, but a package file edited by
 * hand afterwards would reach here unchecked, and an unknown state would leave
 * the pet frozen mid-action with nothing on screen to explain it.
 */
function readActions(value: unknown): Record<string, DesktopPetActionState> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, DesktopPetActionState> = {};
  for (const [name, state] of Object.entries(value)) {
    if (typeof state === "string" && actionStates.has(state)) {
      result[name] = state as DesktopPetActionState;
    }
  }
  return result;
}
