import { useState } from "react";
import { useAccounts } from "../accounts/useAccounts";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState, usePluginRosterLoaded } from "../plugins/usePluginEnabledState";
import { toFileUrl } from "../shared/format";
import type { RoleRecord } from "../shared/types";
import { PhoneConversationList } from "./PhoneConversationList";
import { PhoneHomeScreen } from "./PhoneHomeScreen";
import { accountConversations, phoneApps } from "./phonePresentation";
import { PhoneShell } from "./PhoneShell";
import { usePhoneClock } from "./usePhoneClock";
import { usePhoneConversations } from "./usePhoneConversations";

/** Which screen shows, and the side it slides in from (`none` for the first one). */
type PhoneView = { accountId: string | null; direction: "none" | "forward" | "back" };

/**
 * The role's phone, floating at the right of the chat: home screen of the
 * role's accounts, then one account's conversations. Mounting it (opening
 * the phone) reads the accounts and conversations afresh.
 */
export function PhonePanel({ role }: { role: RoleRecord }) {
  const now = usePhoneClock();
  const { accounts, error: accountsError, reload: reloadAccounts } = useAccounts();
  const { conversations, error: conversationsError, refresh: refreshConversations } = usePhoneConversations(role.id);
  const isPluginEnabled = usePluginEnabledState();
  const rosterLoaded = usePluginRosterLoaded();
  const [view, setView] = useState<PhoneView>({ accountId: null, direction: "none" });
  // Until the plugin roster loads no channel label is known yet; wait rather than show fallback names.
  const apps = accounts && rosterLoaded
    ? phoneApps(accounts, role.id, (pluginId) => pluginUiRegistry.getAccountDetail(pluginId, isPluginEnabled))
    : null;
  // An app whose account went away leaves nothing to show but the home screen.
  const openApp = apps?.find((app) => app.accountId === view.accountId) ?? null;
  return (
    <aside className="pointer-events-auto flex h-full justify-end" aria-label={`${role.name} 的手机`} data-testid="phone-panel">
      <PhoneShell avatarUrl={role.avatar_abs ? toFileUrl(role.avatar_abs) : ""} now={now}>
        <div key={openApp?.accountId ?? "home"} className="phone-view h-full" data-direction={view.direction}>
          {openApp ? (
            <PhoneConversationList
              app={openApp}
              conversations={conversations && accountConversations(conversations, openApp.accountId)}
              error={conversationsError}
              now={now}
              onRetry={() => void refreshConversations()}
              onBack={() => setView({ accountId: null, direction: "back" })}
            />
          ) : (
            <PhoneHomeScreen
              apps={apps}
              error={accountsError}
              onRetry={() => void reloadAccounts()}
              onOpen={(accountId) => setView({ accountId, direction: "forward" })}
            />
          )}
        </div>
      </PhoneShell>
    </aside>
  );
}
