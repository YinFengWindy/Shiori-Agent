import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

/** One Bot credential stored only in Telegram's plugin configuration. */
export type TelegramBotEntry = { ref: string; token: string; enabled: boolean };

/** Normalize the old single Token into the stable legacy account reference. */
export function telegramBots(config: PluginConfigSnapshot): TelegramBotEntry[] {
  const values = config.values;
  const bots = Array.isArray(values.bots) ? values.bots.flatMap((item) => {
    if (!item || typeof item !== "object" || !("ref" in item) || !("token" in item)) return [];
    if (typeof item.ref !== "string" || typeof item.token !== "string") return [];
    return [{ ref: item.ref, token: item.token, enabled: !("enabled" in item) || item.enabled !== false }];
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

/** Build an explicit config update while preserving unrelated Bot credentials. */
export function withTelegramBot(
  config: PluginConfigSnapshot,
  ref: string,
  token: string | undefined,
  enabled: boolean,
) {
  const bots = telegramBots(config);
  const index = bots.findIndex((bot) => bot.ref === ref);
  if (index < 0) {
    if (!token) throw new Error("新账号需要 Bot Token");
    bots.push({ ref, token, enabled });
  } else {
    bots[index] = { ...bots[index], token: token || bots[index].token, enabled };
  }
  return { ...config.values, token: "", bots };
}
