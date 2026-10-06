import { createRequire } from "node:module";
import { matchesHotkey, parseHotkey } from "./hotkey.js";

type KeyEvent = Parameters<typeof matchesHotkey>[0];
/** Process-wide keyboard source; shared subscriptions never stop another owner's hook. */
export type KeyboardHook = {
  on(name: "keydown" | "keyup", listener: (event: KeyEvent) => void): unknown;
  off(name: "keydown" | "keyup", listener: (event: KeyEvent) => void): unknown;
  start(): void;
  stop(): void;
};

/** Owns native key registrations without assigning application semantics to any key. */
export class PluginGlobalKeys {
  private readonly entries = new Map<string, { hotkey: NonNullable<ReturnType<typeof parseHotkey>>; down: boolean; listener: (phase: "down" | "up") => void }>();
  private hook: KeyboardHook | null = null;
  private readonly down = (event: KeyEvent) => this.dispatch(event, "down");
  private readonly up = (event: KeyEvent) => this.dispatch(event, "up");
  constructor(private readonly load = () => createRequire(import.meta.url)("uiohook-napi").uIOhook as KeyboardHook) {}

  /** Replaces only this session's named registration. */
  register(owner: string, id: string, accelerator: string, listener: (phase: "down" | "up") => void) {
    const hotkey = parseHotkey(accelerator);
    if (!hotkey || !id) throw new Error("快捷键格式无效");
    if (!this.hook) {
      const hook = this.load();
      hook.on("keydown", this.down); hook.on("keyup", this.up);
      try { hook.start(); } catch (error) { hook.off("keydown", this.down); hook.off("keyup", this.up); throw error; }
      this.hook = hook;
    }
    const key = JSON.stringify([owner, id]);
    const previous = this.entries.get(key);
    if (previous?.down) previous.listener("up");
    this.entries.set(key, { hotkey, down: false, listener });
  }

  /** Releases one named registration, or all registrations for an ending session. */
  release(owner: string, id?: string) {
    for (const key of this.entries.keys()) {
      const [candidateOwner, candidateId] = JSON.parse(key) as [string, string];
      if (candidateOwner === owner && (id === undefined || id === candidateId)) this.entries.delete(key);
    }
    if (!this.entries.size && this.hook) {
      this.hook.off("keydown", this.down); this.hook.off("keyup", this.up); this.hook.stop(); this.hook = null;
    }
  }

  private dispatch(event: KeyEvent, phase: "down" | "up") {
    for (const entry of this.entries.values()) {
      if (phase === "down" ? !entry.down && matchesHotkey(event, entry.hotkey) : entry.down && event.keycode === entry.hotkey.keycode) {
        entry.down = phase === "down";
        entry.listener(phase);
      }
    }
  }
}
