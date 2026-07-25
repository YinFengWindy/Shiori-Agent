import { UiohookKey, uIOhook, type UiohookKeyboardEvent } from "uiohook-napi";
import type { VoiceInputSource } from "./interactionState.js";

type KeyboardHook = {
  on(event: "keydown" | "keyup", listener: (event: UiohookKeyboardEvent) => void): KeyboardHook;
  off?(event: "keydown" | "keyup", listener: (event: UiohookKeyboardEvent) => void): KeyboardHook;
  removeListener?(event: "keydown" | "keyup", listener: (event: UiohookKeyboardEvent) => void): KeyboardHook;
  start(): void;
  stop(): void;
};

/** Voice lifecycle callbacks invoked by the process-wide keyboard hook. */
export type VoiceHotkeyCallbacks = {
  onPress(source: VoiceInputSource): void;
  onRelease(source: VoiceInputSource): void;
  onCancel(): void;
};

/** Parses and owns the process-wide keydown/keyup hook for desktop voice input. */
export class VoiceHotkeyController {
  private readonly onKeyDownBound = (event: UiohookKeyboardEvent) => this.onKeyDown(event);
  private readonly onKeyUpBound = (event: UiohookKeyboardEvent) => this.onKeyUp(event);
  private hotkey: ParsedHotkey | null = null;
  private registered = false;
  private pressed = false;

  constructor(
    private readonly callbacks: VoiceHotkeyCallbacks,
    private readonly hook: KeyboardHook = uIOhook,
  ) {}

  /** Sets the user-visible accelerator; an empty value disables it. */
  setHotkey(value: string): boolean {
    const parsed = parseHotkey(value);
    this.hotkey = parsed;
    if (this.registered) this.restartHook();
    return parsed !== null || value.trim() === "";
  }

  /** Registers the global hook only when a valid hotkey is configured. */
  start(): boolean {
    if (this.registered || !this.hotkey) return Boolean(this.hotkey);
    this.hook.on("keydown", this.onKeyDownBound).on("keyup", this.onKeyUpBound);
    this.hook.start();
    this.registered = true;
    return true;
  }

  /** Releases the global hook and clears a half-pressed hotkey. */
  stop(): void {
    if (!this.registered) return;
    this.hook.off?.("keydown", this.onKeyDownBound).off?.("keyup", this.onKeyUpBound);
    this.hook.removeListener?.("keydown", this.onKeyDownBound).removeListener?.("keyup", this.onKeyUpBound);
    this.hook.stop();
    this.registered = false;
    this.pressed = false;
  }

  private restartHook(): void {
    const wasRegistered = this.registered;
    this.stop();
    if (wasRegistered) this.start();
  }

  private onKeyDown(event: UiohookKeyboardEvent): void {
    if (event.keycode === UiohookKey.Escape) {
      this.callbacks.onCancel();
      return;
    }
    if (!this.hotkey || this.pressed || !matchesHotkey(event, this.hotkey)) return;
    this.pressed = true;
    this.callbacks.onPress("hotkey");
  }

  private onKeyUp(event: UiohookKeyboardEvent): void {
    if (!this.hotkey || !this.pressed || event.keycode !== this.hotkey.keycode) return;
    this.pressed = false;
    this.callbacks.onRelease("hotkey");
  }
}

type ParsedHotkey = {
  keycode: number;
  ctrl: boolean;
  alt: boolean;
  shift: boolean;
  meta: boolean;
};

/** Converts a user-facing accelerator such as Ctrl+Space to uiohook fields. */
export function parseHotkey(value: string): ParsedHotkey | null {
  const parts = value.split("+").map((part) => part.trim().toLowerCase()).filter(Boolean);
  if (parts.length < 2) return null;
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

function matchesHotkey(event: UiohookKeyboardEvent, hotkey: ParsedHotkey): boolean {
  return event.keycode === hotkey.keycode
    && event.ctrlKey === hotkey.ctrl
    && event.altKey === hotkey.alt
    && event.shiftKey === hotkey.shift
    && event.metaKey === hotkey.meta;
}

function keyCodeForName(value: string): number | null {
  if (value === "space") return UiohookKey.Space;
  if (value === "escape" || value === "esc") return UiohookKey.Escape;
  const key = value.length === 1 ? value.toUpperCase() : value;
  const candidate = (UiohookKey as Record<string, number>)[key];
  return typeof candidate === "number" ? candidate : null;
}
