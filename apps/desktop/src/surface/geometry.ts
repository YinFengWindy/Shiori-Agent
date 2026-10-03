import type { SurfaceExtension, SurfaceWorkArea } from "@yinfengwindy/shiori-sdk/contract";
import type { SurfaceBody, SurfaceBounds, SurfacePoint } from "./contract.js";

/**
 * Clamps a surface's *body* fully inside a display work area.
 *
 * Only the body is constrained: a surface with an extension (a panel grown
 * above or below it) must not be pushed around the screen just because that
 * panel appeared. See `surfaceWindowBounds` for how the two combine.
 *
 * A body larger than the work area has no position that satisfies both edges;
 * rather than let `Math.min`/`Math.max` silently produce an off-screen origin
 * — which is what a naive two-sided clamp does when the upper bound falls
 * below the lower one — the work-area origin wins, keeping the surface's
 * top-left corner reachable.
 */
export function clampSurfaceAnchor(
  anchor: SurfacePoint,
  body: SurfaceBody,
  workArea: SurfaceWorkArea,
): SurfacePoint {
  return {
    x: clampAxis(anchor.x, body.width, workArea.x, workArea.width),
    y: clampAxis(anchor.y, body.height, workArea.y, workArea.height),
  };
}

function clampAxis(value: number, size: number, origin: number, available: number): number {
  const limit = origin + available - size;
  if (limit <= origin) return origin;
  return Math.min(Math.max(value, origin), limit);
}

/**
 * Resolves the window rectangle for a body anchor plus an optional extension.
 *
 * An `above` extension moves the window origin up and grows its height, so the
 * body still renders at `anchor`; a `below` extension only grows the height.
 * The renderer therefore always draws its body at the window-local offset
 * reported by `surfaceBodyOffset`.
 */
export function surfaceWindowBounds(
  anchor: SurfacePoint,
  body: SurfaceBody,
  extension: SurfaceExtension,
): SurfaceBounds {
  const size = normalizedExtensionSize(extension);
  return {
    x: anchor.x,
    y: extension.side === "above" ? anchor.y - size : anchor.y,
    width: body.width,
    height: body.height + size,
  };
}

/**
 * Where the body sits inside its own window, so the renderer can lay itself
 * out without recomputing the extension arithmetic.
 */
export function surfaceBodyOffset(extension: SurfaceExtension): SurfacePoint {
  return { x: 0, y: extension.side === "above" ? normalizedExtensionSize(extension) : 0 };
}

/**
 * Recovers the body anchor from a window rectangle.
 *
 * Needed whenever the authoritative position lives in the OS rather than in
 * memory — for example after the user moves the window, or when restoring a
 * surface whose in-memory anchor was dropped.
 */
export function surfaceAnchorFromWindowBounds(
  bounds: SurfaceBounds,
  extension: SurfaceExtension,
): SurfacePoint {
  const size = normalizedExtensionSize(extension);
  return {
    x: bounds.x,
    y: extension.side === "above" ? bounds.y + size : bounds.y,
  };
}

/** Converts the system cursor location into a body anchor via the pointer's grab offset. */
export function surfaceAnchorFromCursor(
  cursor: SurfacePoint,
  pointerOffset: SurfacePoint,
): SurfacePoint {
  return { x: cursor.x - pointerOffset.x, y: cursor.y - pointerOffset.y };
}

/**
 * Rejects the fractional and negative extension sizes a renderer can produce
 * from a measured DOM height, so window bounds are always whole pixels.
 */
function normalizedExtensionSize(extension: SurfaceExtension): number {
  if (!Number.isFinite(extension.size)) return 0;
  return Math.max(0, Math.ceil(extension.size));
}
