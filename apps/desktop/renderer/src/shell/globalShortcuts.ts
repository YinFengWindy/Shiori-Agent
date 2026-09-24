/**
 * App-wide keyboard shortcuts for the workspace shell: Ctrl+K search,
 * Ctrl+, settings, Ctrl+1…9 the nav rail's views in rail order. Escape is
 * not handled here — every dialog/overlay keeps owning its own Escape.
 */

/** What a shortcut asks the shell to do. `view` indexes the rail's view entries (0-based). */
export type GlobalShortcutAction =
  | { kind: "search" }
  | { kind: "settings" }
  | { kind: "view"; index: number };

/** The subset of `KeyboardEvent` the resolver reads (kept structural so tests need no DOM). */
export type ShortcutKeyEvent = Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "isComposing" | "keyCode" | "repeat">;

/** Maximum number of rail views reachable by Ctrl+digit. */
export const maxViewShortcuts = 9;

/** Whether this platform uses ⌘ rather than Ctrl as the shortcut modifier. */
export function usesMetaModifier(platform = typeof navigator === "undefined" ? "" : navigator.platform): boolean {
  return /mac/i.test(platform);
}

/** Human label for a shortcut key under the platform modifier, e.g. 「Ctrl+K」 / 「⌘K」. */
export function formatShortcut(key: string, meta = usesMetaModifier()): string {
  return meta ? `⌘${key}` : `Ctrl+${key}`;
}

/** Label for the rail view at `index`, or undefined past the digit range. */
export function viewShortcutLabel(index: number, meta = usesMetaModifier()): string | undefined {
  return index >= 0 && index < maxViewShortcuts ? formatShortcut(String(index + 1), meta) : undefined;
}

/**
 * Maps one keydown to a shell action, or null when it is not ours.
 *
 * Ignored: IME composition (the key belongs to the candidate window, and
 * keyCode 229 is what Chromium reports while composing), auto-repeat, and
 * any chord with Alt or Shift so AltGr layouts and Ctrl+Shift+… editor
 * bindings pass through. Ctrl+K / Ctrl+, / Ctrl+digit have no text-editing
 * meaning in a plain input or textarea, so they stay live while typing.
 * `event.code` is read first so the physical key works on any layout; the
 * character is the fallback for synthetic events without a code.
 */
export function resolveGlobalShortcut(event: ShortcutKeyEvent, meta = usesMetaModifier()): GlobalShortcutAction | null {
  if (event.isComposing || event.keyCode === 229 || event.repeat) return null;
  const modifier = meta ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
  if (!modifier || event.altKey || event.shiftKey) return null;
  const key = event.key.toLowerCase();
  if (event.code === "KeyK" || (!event.code && key === "k")) return { kind: "search" };
  if (event.code === "Comma" || (!event.code && key === ",")) return { kind: "settings" };
  const digit = /^Digit([1-9])$/.exec(event.code)?.[1] ?? (!event.code && /^[1-9]$/.test(key) ? key : undefined);
  if (digit) return { kind: "view", index: Number(digit) - 1 };
  return null;
}
