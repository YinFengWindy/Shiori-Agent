import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

/** One Bot credential stored only in Telegram's plugin configuration, with the role owning it. */
export type TelegramBotEntry = { ref: string; token: string; enabled: boolean; role_id?: string };

/** Normalize the old single Token into the stable legacy account reference. */
export function telegramBots(config: PluginConfigSnapshot): TelegramBotEntry[] {
  const values = config.values;
  const bots = Array.isArray(values.bots) ? values.bots.flatMap((item) => {
    if (!item || typeof item !== "object" || !("ref" in item) || !("token" in item)) return [];
    if (typeof item.ref !== "string" || typeof item.token !== "string") return [];
    const roleId = "role_id" in item && typeof item.role_id === "string" && item.role_id ? { role_id: item.role_id } : {};
    return [{ ref: item.ref, token: item.token, enabled: !("enabled" in item) || item.enabled !== false, ...roleId }];
  }) : [];
  if (typeof values.token === "string" && values.token && !bots.some((bot) => bot.ref === "legacy")) {
    bots.unshift({ ref: "legacy", token: values.token, enabled: true });
  }
  return bots;
}

/** A saved single Token without an account row should be repaired in place. */
export function legacyRefToRepair(config: PluginConfigSnapshot): "legacy" | null {
  const values = config.values;
  if (typeof values.token !== "string" || !values.token.trim()) return null;
  if (Array.isArray(values.bots) && values.bots.some((item) => item && typeof item === "object" && "ref" in item && item.ref === "legacy")) return null;
  return "legacy";
}

/**
 * Build an explicit config update while preserving unrelated Bot credentials.
 * The Bot belongs to `roleId`, the role it is saved from; an owned Bot keeps its owner.
 */
export function withTelegramBot(
  config: PluginConfigSnapshot,
  ref: string,
  token: string | undefined,
  enabled: boolean,
  roleId: string,
) {
  const bots = telegramBots(config);
  const index = bots.findIndex((bot) => bot.ref === ref);
  if (index < 0) {
    if (!token) throw new Error("新账号需要 Bot Token");
    bots.push({ ref, token, enabled, role_id: roleId });
  } else {
    bots[index] = { ...bots[index], token: token || bots[index].token, enabled, role_id: bots[index].role_id || roleId };
  }
  return { ...config.values, token: "", bots };
}
