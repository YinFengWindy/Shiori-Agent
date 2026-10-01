import { useState } from "react";
import { useAccounts } from "../accounts/useAccounts";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState, usePluginRosterLoaded } from "../plugins/usePluginEnabledState";
import { toFileUrl } from "../shared/format";
import type { RoleRecord } from "@shiori/sdk";
import { PhoneConversationList } from "./PhoneConversationList";
import { PhoneConversationScreens } from "./PhoneConversationScreens";
import { PhoneHomeScreen } from "./PhoneHomeScreen";
import { PhoneSettingsPage } from "./PhoneSettingsPage";
import { accountConversations, phoneApps } from "./phonePresentation";
import { PhoneShell } from "./PhoneShell";
import { usePhoneClock } from "./usePhoneClock";
import { usePhoneConversations } from "./usePhoneConversations";

/**
 * Which screen shows: the home screen, the phone's settings, or an app:
 * its conversation list (no thread) or a conversation's chat page; and the
 * side it slides in from (`none` for the first one).
 */
type PhoneView = (
  | { kind: "home" }
  | { kind: "settings" }
  | { kind: "app"; accountId: string; threadId: string | null }
) & { direction: "none" | "forward" | "back" };

const homeView: PhoneView = { kind: "home", direction: "none" };

/**
 * The role's phone, floating at the right of the chat: home screen of the
 * role's accounts (and the phone's settings), then one account's conversations, then one
 * conversation (with its chat info and member profiles). Mounting it (opening the phone) reads the accounts and
 * conversations afresh; while it is open, new messages arrive live.
 */
export function PhonePanel({ role }: { role: RoleRecord }) {
  const now = usePhoneClock();
  const { accounts, error: accountsError, reload: reloadAccounts } = useAccounts();
  const { conversations, error: conversationsError, refresh: refreshConversations } = usePhoneConversations(role.id);
  const isPluginEnabled = usePluginEnabledState();
  const rosterLoaded = usePluginRosterLoaded();
  const [view, setView] = useState(homeView);
  // Until the plugin roster loads no channel label is known yet; wait rather than show fallback names.
  const apps = accounts && rosterLoaded
    ? phoneApps(accounts, role.id, (pluginId) => pluginUiRegistry.getAccountDetail(pluginId, isPluginEnabled))
    : null;
  // An app whose account went away leaves nothing to show but the home screen.
  const openApp = view.kind === "app" ? apps?.find((app) => app.accountId === view.accountId) ?? null : null;
  const appConversations = openApp && conversations && accountConversations(conversations, openApp.accountId);
  // Likewise a conversation that left the app (e.g. rebound to another role) returns to its list.
  const openThreadId = view.kind === "app" ? view.threadId : null;
  const openConversation = appConversations?.find((conversation) => conversation.threadId === openThreadId) ?? null;
  return (
    <aside className="pointer-events-auto flex h-full justify-end" aria-label={`${role.name} 的手机`} data-testid="phone-panel">
      <PhoneShell avatarUrl={role.avatar_abs ? toFileUrl(role.avatar_abs) : ""} now={now}>
        <div key={openConversation?.threadId ?? openApp?.accountId ?? view.kind} className="phone-view h-full"
          data-direction={view.direction}>
          {view.kind === "settings" ? (
            <PhoneSettingsPage onBack={() => setView({ ...homeView, direction: "back" })} />
          ) : openApp && openConversation ? (
            <PhoneConversationScreens
              role={role}
              app={openApp}
              conversation={openConversation}
              now={now}
              onBack={() => setView({ kind: "app", accountId: openApp.accountId, threadId: null, direction: "back" })}
            />
          ) : openApp ? (
            <PhoneConversationList
              app={openApp}
              conversations={appConversations}
              error={conversationsError}
              now={now}
              onRetry={() => void refreshConversations()}
              onBack={() => setView({ ...homeView, direction: "back" })}
              onOpen={(threadId) => setView({ kind: "app", accountId: openApp.accountId, threadId, direction: "forward" })}
            />
          ) : (
            <PhoneHomeScreen
              apps={apps}
              error={accountsError}
              onRetry={() => void reloadAccounts()}
              onOpen={(accountId) => setView({ kind: "app", accountId, threadId: null, direction: "forward" })}
              onOpenSettings={() => setView({ kind: "settings", direction: "forward" })}
            />
          )}
        </div>
      </PhoneShell>
    </aside>
  );
}
