/** Stable uiohook key codes used by the persisted desktop hotkey setting. */
export const UiohookKey = {
  Backspace: 14,
  Tab: 15,
  Enter: 28,
  CapsLock: 58,
  Escape: 1,
  Space: 57,
  PageUp: 3657,
  PageDown: 3665,
  End: 3663,
  Home: 3655,
  ArrowLeft: 57419,
  ArrowUp: 57416,
  ArrowRight: 57421,
  ArrowDown: 57424,
  Insert: 3666,
  Delete: 3667,
  0: 11,
  1: 2,
  2: 3,
  3: 4,
  4: 5,
  5: 6,
  6: 7,
  7: 8,
  8: 9,
  9: 10,
  Numpad0: 82,
  Numpad1: 79,
  Numpad2: 80,
  Numpad3: 81,
  Numpad4: 75,
  Numpad5: 76,
  Numpad6: 77,
  Numpad7: 71,
  Numpad8: 72,
  Numpad9: 73,
  NumpadMultiply: 55,
  NumpadAdd: 78,
  NumpadSubtract: 74,
  NumpadDecimal: 83,
  NumpadDivide: 3637,
  NumpadEnter: 28,
  NumpadEnd: 61007,
  NumpadArrowDown: 61008,
  NumpadPageDown: 61009,
  NumpadArrowLeft: 61003,
  NumpadArrowRight: 61005,
  NumpadHome: 60999,
  NumpadArrowUp: 61000,
  NumpadPageUp: 61001,
  NumpadInsert: 61010,
  NumpadDelete: 61011,
  A: 30,
  B: 48,
  C: 46,
  D: 32,
  E: 18,
  F: 33,
  G: 34,
  H: 35,
  I: 23,
  J: 36,
  K: 37,
  L: 38,
  M: 50,
  N: 49,
  O: 24,
  P: 25,
  Q: 16,
  R: 19,
  S: 31,
  T: 20,
  U: 22,
  V: 47,
  W: 17,
  X: 45,
  Y: 21,
  Z: 44,
  F1: 59,
  F2: 60,
  F3: 61,
  F4: 62,
  F5: 63,
  F6: 64,
  F7: 65,
  F8: 66,
  F9: 67,
  F10: 68,
  F11: 87,
  F12: 88,
  F13: 91,
  F14: 92,
  F15: 93,
  F16: 99,
  F17: 100,
  F18: 101,
  F19: 102,
  F20: 103,
  F21: 104,
  F22: 105,
  F23: 106,
  F24: 107,
  Semicolon: 39,
  Equal: 13,
  Comma: 51,
  Minus: 12,
  Period: 52,
  Slash: 53,
  Backquote: 41,
  BracketLeft: 26,
  Backslash: 43,
  BracketRight: 27,
  Quote: 40,
  Ctrl: 29,
  CtrlRight: 3613,
  Alt: 56,
  AltRight: 3640,
  Shift: 42,
  ShiftRight: 54,
  Meta: 3675,
  MetaRight: 3676,
  NumLock: 69,
  ScrollLock: 70,
  PrintScreen: 3639,
} as const;

/** Physical key and exact modifier state for a generic accelerator. */
export type ParsedHotkey = {
  keycode: number;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  meta: boolean;
};

/** Converts a user-facing accelerator such as Ctrl+Space to uiohook fields. */
export function parseHotkey(value: string): ParsedHotkey | null {
  const parts = value.split("+").map((part) => part.trim().toLowerCase()).filter(Boolean);
  if (parts.length < 1) return null;
  const keyName = parts.at(-1) ?? "";
  const keycode = keyCodeForName(keyName);
  if (keycode === null) return null;
  const modifiers = new Set(parts.slice(0, -1));
  if ([...modifiers].some((modifier) => !["ctrl", "control", "alt", "shift", "meta", "command"].includes(modifier))) return null;
  return {
    keycode,
    ctrl: modifiers.has("ctrl") || modifiers.has("control"),
    alt: modifiers.has("alt"),
    shift: modifiers.has("shift"),
    meta: modifiers.has("meta") || modifiers.has("command"),
  };
}

/** Matches an accelerator without assigning meaning to the resulting key edge. */
export function matchesHotkey(event: { keycode: number; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }, hotkey: ParsedHotkey): boolean {
  return event.keycode === hotkey.keycode
    && event.ctrlKey === hotkey.ctrl
    && event.altKey === hotkey.alt
    && event.shiftKey === hotkey.shift
    && event.metaKey === hotkey.meta;
}

function keyCodeForName(value: string): number | null {
  if (value === "space") return UiohookKey.Space;
  if (value === "escape" || value === "esc") return UiohookKey.Escape;
  return Object.entries(UiohookKey).find(([name]) => name.toLowerCase() === value.toLowerCase())?.[1] ?? null;
}
