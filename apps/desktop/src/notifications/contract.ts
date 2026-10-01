/** A notification click retained by main until its chat has opened successfully. */
export type NotificationChatTarget = {
  id: number;
  roleId: string;
};

/** Main-window notification navigation, including clicks received during reload. */
export type DesktopNotificationsApi = {
  getPending(): Promise<NotificationChatTarget | null>;
  acknowledge(id: number): Promise<void>;
  onClicked(listener: () => void): () => void;
};

/** Private main/preload channels for notification click delivery. */
export const notificationChannels = {
  pending: "desktop:notification-pending",
  acknowledge: "desktop:notification-acknowledge",
  clicked: "desktop:notification-clicked",
} as const;
