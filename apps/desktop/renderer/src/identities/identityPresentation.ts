import type { AccountSnapshot } from "../accounts/accountClient";
import { accountName } from "../accounts/accountPresentation";
import type { AccountDetailEntry } from "../plugins/pluginUiRegistry";
import type { UserIdentity } from "./identityClient";

/** The channel's name and mark; a plugin without account controls shows its id and the generic mark. */
export function identityChannel(identity: UserIdentity, channels: AccountDetailEntry[]) {
  const channel = channels.find((item) => item.pluginId === identity.pluginId);
  return { label: channel?.label ?? identity.pluginId, Icon: channel?.Icon };
}

/**
 * Where a binding is recognized: 全平台 for platform scope, otherwise the
 * account's name while it is loaded, else its raw id.
 */
export function identityScopeLabel(identity: UserIdentity, accounts: AccountSnapshot[] | null) {
  if (identity.scope === "platform") return "全平台";
  const account = accounts?.find((item) => item.id === identity.accountId);
  return `仅 ${account ? accountName(account) : identity.accountId}`;
}

/** Remaining time as `m:ss`, floored to whole seconds and never negative. */
export function formatCountdown(remainingMs: number) {
  const seconds = Math.max(0, Math.floor(remainingMs / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Keys that change when an identity is newly bound or re-bound (the host
 * refreshes `boundAt` whenever a pairing code binds an existing identity),
 * but not when only its known chats change.
 */
export function identityBindingKeys(identities: UserIdentity[]) {
  return new Set(identities.map((item) => `${item.id}@${item.boundAt}`));
}
