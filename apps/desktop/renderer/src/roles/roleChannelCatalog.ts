import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding } from "../shared/types";
import type { SelectOption } from "../shared/ui/Select";

/** The `channels.list` rows the role delivery panels read; null until the first load succeeds. */
export type RoleChannelCatalog = readonly ChannelSummary[] | null;

/** The host-owned transport that always exists and never comes from a plugin. */
export const desktopChannelName = "desktop";

const desktopChannelLabel = "桌面端";

/**
 * How one existing binding may be edited:
 * - `editable`: its channel is offered by an enabled provider (or the catalog is still loading);
 * - `plugin_disabled`: the providing plugin is disabled, so the binding stays visible read-only;
 * - `missing`: no provider declares the channel anymore (plugin uninstalled), also read-only.
 * Read-only bindings keep their data and can still be reordered or removed.
 */
export type RoleBindingAvailability =
  | { kind: "editable"; channel: ChannelSummary | null }
  | { kind: "plugin_disabled"; channel: ChannelSummary }
  | { kind: "missing" };

/** Finds the catalog row for one channel name. */
export function findRoleChannel(catalog: RoleChannelCatalog, channel: string): ChannelSummary | null {
  return catalog?.find((item) => item.name === channel) ?? null;
}

/** Returns the display label for a bound channel, falling back to its raw name. */
export function roleChannelLabel(channel: string, catalog: RoleChannelCatalog): string {
  if (channel === desktopChannelName) return desktopChannelLabel;
  return findRoleChannel(catalog, channel)?.label ?? channel;
}

/** Whether a new binding may target this channel: its provider must be enabled. */
function isSelectableChannel(channel: ChannelSummary): boolean {
  return channel.state !== "plugin_disabled";
}

/** Short marker appended to a selectable channel that cannot deliver yet. */
export function roleChannelStateMarker(channel: ChannelSummary): string {
  if (channel.state === "not_configured") return "未配置";
  if (channel.state === "failed") return "异常";
  return "";
}

/** Classifies an existing binding against the current catalog. */
export function roleBindingAvailability(binding: RoleChannelBinding, catalog: RoleChannelCatalog): RoleBindingAvailability {
  if (binding.channel === desktopChannelName || catalog === null) {
    return { kind: "editable", channel: findRoleChannel(catalog, binding.channel) };
  }
  const channel = findRoleChannel(catalog, binding.channel);
  if (!channel) return { kind: "missing" };
  if (!isSelectableChannel(channel)) return { kind: "plugin_disabled", channel };
  return { kind: "editable", channel };
}

/**
 * Channel picker options: every channel whose provider is enabled (external
 * ones first, desktop last), with not-yet-usable ones marked in the list
 * only; the closed trigger shows the plain label next to the row badge. While the
 * catalog is loading only the binding's own channel is offered, so the
 * picker never shows a value it cannot label.
 */
export function roleBindingChannelOptions(catalog: RoleChannelCatalog, currentChannel: string): SelectOption[] {
  if (catalog === null) {
    return [{ value: currentChannel, label: roleChannelLabel(currentChannel, catalog) }];
  }
  const external = catalog
    .filter((channel) => channel.name !== desktopChannelName && isSelectableChannel(channel))
    .map((channel) => {
      const marker = roleChannelStateMarker(channel);
      return { value: channel.name, label: marker ? `${channel.label}（${marker}）` : channel.label, triggerLabel: channel.label };
    });
  return [...external, { value: desktopChannelName, label: desktopChannelLabel }];
}

/** Picks the channel for a new binding: the first working external channel, else any enabled one, else desktop. */
export function defaultRoleBindingChannel(catalog: RoleChannelCatalog): string {
  const external = (catalog ?? []).filter((channel) => channel.name !== desktopChannelName && isSelectableChannel(channel));
  return (external.find((channel) => channel.state === "active") ?? external[0])?.name ?? desktopChannelName;
}

/** Label for the binding's sole external contact, qualified by the channel's declared identity. */
export function roleBindingContactLabel(channel: ChannelSummary | null): string {
  return channel?.contactLabel ? `联系人 ID（${channel.contactLabel}）` : "联系人 ID";
}
