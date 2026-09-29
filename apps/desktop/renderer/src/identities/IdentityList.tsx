import { LinkBreakIcon } from "@phosphor-icons/react";
import { AccountAvatar } from "../accounts/AccountAvatar";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import type { AccountDetailEntry } from "../plugins/pluginUiRegistry";
import { formatTimestamp } from "../shared/format";
import { compactDangerTextButtonClass } from "../shared/styles";
import { SettingsGroup } from "../settings/SettingsFieldPrimitives";
import type { UserIdentity } from "./identityClient";
import { identityChannel, identityScopeLabel } from "./identityPresentation";

/**
 * One row per bound identity: channel mark and name, the platform user id,
 * where it is recognized, when it was bound, and an unbind action.
 */
export function IdentityList({ identities, channels, accounts, onUnbind }: {
  identities: UserIdentity[];
  /** Channel marks and names, by plugin. */
  channels: AccountDetailEntry[];
  accounts: AccountSnapshot[] | null;
  onUnbind: (identity: UserIdentity) => void;
}) {
  return <SettingsGroup title="已绑定">
    <ul className="m-0 grid list-none p-0">
      {identities.map((identity) => {
        const channel = identityChannel(identity, channels);
        return <li key={identity.id} className="flex min-w-0 items-center gap-3 border-b border-line-soft py-3.5 last:border-b-0">
          <AccountAvatar avatarUrl="" Icon={channel.Icon} />
          <span className="grid min-w-0 flex-1 gap-0.5">
            <span className="flex min-w-0 items-baseline gap-2">
              <span className="shrink-0 text-body font-medium text-ink">{channel.label}</span>
              <span className="truncate font-mono text-body-sm text-ink-secondary">{identity.userId}</span>
            </span>
            <span className="truncate text-body-sm text-ink-muted">
              {identityScopeLabel(identity, accounts)} · <time dateTime={identity.boundAt}>{formatTimestamp(identity.boundAt)}</time>
            </span>
          </span>
          <button type="button" className={compactDangerTextButtonClass} onClick={() => onUnbind(identity)}>
            <LinkBreakIcon className="h-4 w-4" aria-hidden="true" />解除绑定
          </button>
        </li>;
      })}
    </ul>
  </SettingsGroup>;
}
