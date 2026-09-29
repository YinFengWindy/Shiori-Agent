import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** One platform account of the desktop user, bound through a pairing code. */
export type UserIdentity = {
  id: string;
  pluginId: string;
  /** The user's own id on that platform. */
  userId: string;
  /** `platform`: recognized on every account of the channel; `account`: only on `accountId`. */
  scope: "platform" | "account";
  accountId: string;
  /** ISO time of the binding. */
  boundAt: string;
};

/** A one-time code the user sends from their platform account to bind it. */
export type PairingCode = { code: string; expiresAt: string };

type IdentityPayload = {
  id: string; plugin_id: string; user_id: string;
  scope: UserIdentity["scope"]; account_id: string; bound_at: string;
};

function mapIdentity(row: IdentityPayload): UserIdentity {
  return {
    id: row.id, pluginId: row.plugin_id, userId: row.user_id,
    scope: row.scope, accountId: row.account_id, boundAt: row.bound_at,
  };
}

/** Narrow bridge client for the desktop user's bound identities and pairing codes. */
export function createIdentityClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  return {
    async list() {
      const result = await call<{ identities: IdentityPayload[] }>("identities.list", {});
      return result.identities.map(mapIdentity);
    },
    /** Issues a fresh code; any earlier unexpired code stops being the current one. */
    async createPairingCode(): Promise<PairingCode> {
      const result = await call<{ code: string; expires_at: string }>("identities.pairing.create", {});
      return { code: result.code, expiresAt: result.expires_at };
    },
    async unbind(identityId: string) {
      await call<{ identity_id: string }>("identities.unbind", { identity_id: identityId });
    },
  };
}
