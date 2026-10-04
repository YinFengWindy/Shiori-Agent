import { NotificationNavigation } from "./navigation.js";

/** Encodes a chat target into the app's single supported external activation route. */
export function notificationActivationUrl(protocol: string, roleId: string) {
  return `${protocol}://notification/chat?roleId=${encodeURIComponent(roleId)}`;
}

function parseNotificationTarget(value: string, protocol: string) {
  if (value.length > 4096) return null;
  try {
    const url = new URL(value);
    const roleId = url.searchParams.get("roleId");
    // Canonical equality rejects extra keys, malformed escapes, userinfo, fragments and URL normalization tricks.
    if (!roleId || roleId.length > 512 || /[\p{Cc}\p{Cs}]/u.test(roleId)
      || value !== notificationActivationUrl(protocol, roleId)) return null;
    return roleId;
  } catch {
    // OS activation arguments are untrusted and an invalid URI has no navigation effect.
    return null;
  }
}

/** Queues cold-start activations until the desktop is wired and retains chat targets across reloads. */
export class NotificationActivation {
  readonly navigation = new NotificationNavigation();
  private ready = false;
  private revealRequested = false;

  constructor(private readonly protocol: string | null, private readonly revealWindow: () => void) {}

  /** Handles only the exact notification URI; ordinary process arguments remain inert. */
  handleArguments(args: readonly string[]) {
    const protocol = this.protocol;
    if (!protocol) return false;
    const roleId = [...args].reverse().map((arg) => parseNotificationTarget(arg, protocol)).find((value) => value !== null);
    if (!roleId) return false;
    this.openChat(roleId);
    return true;
  }

  /** Shares the same pending navigation for native clicks and protocol activations. */
  openChat(roleId: string) {
    this.navigation.select(roleId);
    this.requestWindow();
  }

  /** Ordinary second launches also wait for main-process initialization before creating a window. */
  requestWindow() {
    this.revealRequested = true;
    this.flush();
  }

  /** Called only after the IPC handlers and desktop window dependencies have been installed. */
  markReady() {
    this.ready = true;
    this.flush();
  }

  private flush() {
    if (!this.ready || !this.revealRequested) return;
    this.revealWindow();
    this.revealRequested = false;
  }
}
