import type { ChannelSummary } from "../plugins/pluginBridgeClient";

/** Channel snapshots used to label message sources in chat. */
export type RoleChannelCatalog = readonly ChannelSummary[] | null;

/** Returns the display label for a channel, falling back to its raw name. */
export function roleChannelLabel(channel: string, catalog: RoleChannelCatalog): string {
  if (channel === "desktop") return "桌面端";
  return catalog?.find((item) => item.name === channel)?.label ?? channel;
}
