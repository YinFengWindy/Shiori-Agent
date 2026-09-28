import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Account-wide response policy the account's plugin saves with it; every group chat follows it. */
export type AccountResponseRules = {
  privateEnabled: boolean;
  groupEnabled: boolean;
  requireMention: boolean;
  blockedSenderIds: string[];
};

/** An account a loaded plugin registered, joined with its current plugin report. */
export type AccountSnapshot = {
  id: string;
  pluginId: string;
  platform: string;
  platformAccountId: string;
  configRef: string;
  displayName: string;
  avatarUrl: string;
  roleId: string;
  runtimeActive: boolean;
  connection: "unknown" | "connecting" | "online" | "offline" | "login_required" | "error";
  /** `groups` means this account can receive group conversations; other capabilities remain plugin-defined. */
  capabilities: string[];
  error: string;
  responseRules: AccountResponseRules;
};

type AccountPayload = {
  id: string; plugin_id: string; platform: string; platform_account_id: string; config_ref: string;
  display_name: string; avatar_url: string; role_id: string;
  runtime_active: boolean; connection: AccountSnapshot["connection"];
  capabilities: string[]; error: string;
  response_rules: { private_enabled: boolean; group_enabled: boolean; require_mention: boolean; blocked_sender_ids: string[] };
};

function mapAccount(row: AccountPayload): AccountSnapshot {
  return {
    id: row.id, pluginId: row.plugin_id, platform: row.platform,
    platformAccountId: row.platform_account_id, configRef: row.config_ref, displayName: row.display_name,
    avatarUrl: row.avatar_url, roleId: row.role_id,
    runtimeActive: row.runtime_active, connection: row.connection,
    capabilities: row.capabilities, error: row.error,
    responseRules: {
      privateEnabled: row.response_rules.private_enabled,
      groupEnabled: row.response_rules.group_enabled,
      requireMention: row.response_rules.require_mention,
      blockedSenderIds: row.response_rules.blocked_sender_ids,
    },
  };
}

/** Narrow bridge client for account identity, deletion, and common rules. */
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
    /** Deletes a role's account after its plugin purged credentials; history is kept. */
    async remove(accountId: string, roleId: string) {
      await call<{ account_id: string }>("accounts.delete", { account_id: accountId, role_id: roleId });
    },
    async setRules(accountId: string, rules: AccountResponseRules) {
      const result = await call<{ account: AccountPayload }>("accounts.rules.set", {
        account_id: accountId,
        response_rules: {
          private_enabled: rules.privateEnabled,
          group_enabled: rules.groupEnabled,
          require_mention: rules.requireMention,
          blocked_sender_ids: rules.blockedSenderIds,
        },
      });
      return mapAccount(result.account);
    },
  };
}
