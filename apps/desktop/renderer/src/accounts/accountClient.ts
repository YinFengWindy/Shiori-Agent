import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Host-owned policy saved with an account, independent of its assigned role. */
export type AccountResponseRules = {
  privateEnabled: boolean;
  groupEnabled: boolean;
  requireMention: boolean;
  blockedSenderIds: string[];
  groupRules: GroupResponseRule[];
};

/** Group-specific policy keyed by the plugin's real conversation ID. */
export type GroupResponseRule = {
  chatId: string;
  enabled: boolean;
  requireMention: boolean;
  blockedSenderIds: string[];
};

/** Persisted account identity joined with its current plugin report. */
export type AccountSnapshot = {
  id: string;
  pluginId: string;
  platform: string;
  platformAccountId: string;
  configRef: string;
  displayName: string;
  avatarUrl: string;
  roleId: string | null;
  pluginEnabled: boolean;
  runtimeActive: boolean;
  connection: "unknown" | "connecting" | "online" | "offline" | "login_required" | "error";
  /** `groups` means this account can receive group conversations; other capabilities remain plugin-defined. */
  capabilities: string[];
  /** Last non-empty plugin capability report, retained for settings while the plugin is stopped. */
  knownCapabilities: string[];
  error: string;
  responseRules: AccountResponseRules;
};

type AccountPayload = {
  id: string; plugin_id: string; platform: string; platform_account_id: string; config_ref: string;
  display_name: string; avatar_url: string; role_id: string | null;
  plugin_enabled: boolean; runtime_active: boolean; connection: AccountSnapshot["connection"];
  capabilities: string[]; known_capabilities: string[]; error: string;
  response_rules: { private_enabled: boolean; group_enabled: boolean; require_mention: boolean; blocked_sender_ids: string[];
    group_rules: Array<{ chat_id: string; enabled: boolean; require_mention: boolean; blocked_sender_ids: string[] }> };
};

function mapAccount(row: AccountPayload): AccountSnapshot {
  return {
    id: row.id, pluginId: row.plugin_id, platform: row.platform,
    platformAccountId: row.platform_account_id, configRef: row.config_ref, displayName: row.display_name,
    avatarUrl: row.avatar_url, roleId: row.role_id, pluginEnabled: row.plugin_enabled,
    runtimeActive: row.runtime_active, connection: row.connection,
    capabilities: row.capabilities, error: row.error,
    knownCapabilities: row.known_capabilities,
    responseRules: {
      privateEnabled: row.response_rules.private_enabled,
      groupEnabled: row.response_rules.group_enabled,
      requireMention: row.response_rules.require_mention,
      blockedSenderIds: row.response_rules.blocked_sender_ids,
      groupRules: row.response_rules.group_rules.map((group) => ({
        chatId: group.chat_id, enabled: group.enabled, requireMention: group.require_mention,
        blockedSenderIds: group.blocked_sender_ids,
      })),
    },
  };
}

/** Narrow bridge client for account identity, ownership, and common rules. */
export function createAccountClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  return {
    async list(roleId?: string) {
      const result = await call<{ accounts: AccountPayload[] }>("accounts.list", roleId ? { role_id: roleId } : {});
      return result.accounts.map(mapAccount);
    },
    async get(accountId: string) {
      const result = await call<{ account: AccountPayload }>("accounts.get", { account_id: accountId });
      return mapAccount(result.account);
    },
    async assign(accountId: string, roleId: string | null) {
      const result = await call<{ account: AccountPayload }>("accounts.assign", { account_id: accountId, role_id: roleId });
      return mapAccount(result.account);
    },
    async setRules(accountId: string, rules: AccountResponseRules) {
      const result = await call<{ account: AccountPayload }>("accounts.rules.set", {
        account_id: accountId,
        response_rules: {
          private_enabled: rules.privateEnabled,
          group_enabled: rules.groupEnabled,
          require_mention: rules.requireMention,
          blocked_sender_ids: rules.blockedSenderIds,
          group_rules: rules.groupRules.map((group) => ({
            chat_id: group.chatId, enabled: group.enabled,
            require_mention: group.requireMention, blocked_sender_ids: group.blockedSenderIds,
          })),
        },
      });
      return mapAccount(result.account);
    },
  };
}
