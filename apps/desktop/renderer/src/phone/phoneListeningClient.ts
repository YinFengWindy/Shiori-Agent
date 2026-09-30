import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Who turned a group's listening on or off: the user from the phone, or the role with its tool. */
export type PhoneListeningOperator = "user" | "role";

/** One change of a group's listening switch. */
export type PhoneListeningToggle = { enabled: boolean; operator: PhoneListeningOperator; at: string };

/** A group's listening, as its chat info page's 旁听 block shows it. */
export type PhoneListeningState = {
  enabled: boolean;
  /** The group's own daily cap; null when it follows `defaultDailyCap`. */
  dailyCap: number | null;
  defaultDailyCap: number;
  /** The newest changes first. */
  toggles: PhoneListeningToggle[];
};

/** A group's listening state as the bridge sends it. */
type PhoneListeningStatePayload = {
  enabled: boolean; daily_cap: number | null; default_daily_cap: number; toggles: PhoneListeningToggle[];
};

function mapState(row: PhoneListeningStatePayload) {
  return {
    enabled: row.enabled,
    dailyCap: row.daily_cap,
    defaultDailyCap: row.default_daily_cap,
    toggles: row.toggles.map(({ enabled, operator, at }) => ({ enabled, operator, at })),
  } satisfies PhoneListeningState;
}

/**
 * Bridge client for group listening on the phone (#538): one group's
 * switch and daily cap (`threadId`, changed as the user), and the global
 * default cap.
 */
export function createPhoneListeningClient(invoke?: DesktopInvoke) {
  const call = <T>(method: string, payload: Record<string, unknown>) =>
    invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload);
  const group = async (method: string, roleId: string, threadId: string, fields: Record<string, unknown> = {}) =>
    mapState(await call<PhoneListeningStatePayload>(method, { role_id: roleId, thread_id: threadId, ...fields }));
  return {
    readState: (roleId: string, threadId: string) => group("phone.listening.state", roleId, threadId),
    /** Turns listening on or off; the change is logged with the user as operator. */
    setEnabled: (roleId: string, threadId: string, enabled: boolean) =>
      group("phone.listening.set", roleId, threadId, { enabled }),
    /** Overrides the group's daily cap; null follows the default again. */
    setDailyCap: (roleId: string, threadId: string, dailyCap: number | null) =>
      group("phone.listening.cap.set", roleId, threadId, { daily_cap: dailyCap }),
    async readDefaultCap() {
      return (await call<{ default_daily_cap: number }>("phone.listening.defaults", {})).default_daily_cap;
    },
    async saveDefaultCap(dailyCap: number) {
      const result = await call<{ default_daily_cap: number }>("phone.listening.defaults.save", { default_daily_cap: dailyCap });
      return result.default_daily_cap;
    },
  };
}
