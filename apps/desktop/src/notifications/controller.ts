import type { BridgeEvent } from "@shiori/plugin-sdk/contract";
import { notificationMessages } from "./message.js";

/** OS-facing capabilities; notification failures are reported without interrupting bridge delivery. */
export type MessageNotificationHost = {
  isForeground(): boolean;
  isSupported(): boolean;
  show(message: { title: string; body: string }, onClick: () => void): void;
  openChat(roleId: string): void;
  onError(error: unknown): void;
};

/** Deduplicates committed messages and applies main-window foreground policy. */
export class DesktopMessageNotifications {
  private readonly seen = new Set<string>();

  constructor(private readonly host: MessageNotificationHost) {}

  /** Observes a bridge event without allowing OS notification errors to stop message delivery. */
  handleEvent(event: BridgeEvent) {
    try {
      for (const message of notificationMessages(event)) {
        if (this.seen.has(message.key)) continue;
        // Also remember foreground messages: a later duplicate must not become a new alert.
        this.seen.add(message.key);
        if (this.seen.size > 4096) this.seen.delete(this.seen.values().next().value!);
        if (this.host.isForeground() || !this.host.isSupported()) continue;
        this.host.show(message, () => {
          try {
            this.host.openChat(message.roleId);
          } catch (error) {
            this.host.onError(error);
          }
        });
      }
    } catch (error) {
      this.host.onError(error);
    }
  }
}
