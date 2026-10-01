import type { NotificationChatTarget } from "./contract.js";

/** Retains the latest clicked chat across renderer startup, reload and failed opens. */
export class NotificationNavigation {
  private nextId = 0;
  private target: NotificationChatTarget | null = null;

  /** Replaces an older navigation intent with the user's latest click. */
  select(roleId: string) {
    this.target = { id: ++this.nextId, roleId };
  }

  /** Reads without consuming; only a successful renderer navigation can consume it. */
  getPending() {
    return this.target;
  }

  /** An older asynchronous navigation must not consume a more recent click. */
  acknowledge(id: number) {
    if (this.target?.id === id) this.target = null;
  }
}
