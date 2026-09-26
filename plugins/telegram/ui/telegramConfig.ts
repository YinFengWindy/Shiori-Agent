import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

/** One Bot credential stored only in Telegram's plugin configuration. */
export type TelegramBotEntry = { ref: string; token: string; enabled: boolean };

/** Normalize the old single Token into the stable legacy account reference. */
export function telegramBots(config: PluginConfigSnapshot): TelegramBotEntry[] {
  const values = config.values;
  const bots = Array.isArray(values.bots) ? values.bots.flatMap((item) => {
    if (!item || typeof item !== "object" || !("ref" in item) || !("token" in item)) return [];
    const row = item as { ref: unknown; token: unknown; enabled?: unknown };
    if (typeof row.ref !== "string" || typeof row.token !== "string") return [];
    return [{ ref: row.ref, token: row.token, enabled: row.enabled !== false }];
  }) : [];
  if (typeof values.token === "string" && values.token && !bots.some((bot) => bot.ref === "legacy")) {
    bots.unshift({ ref: "legacy", token: values.token, enabled: true });
  }
  return bots;
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
  if (index < 0 && !token) throw new Error("新账号需要 Bot Token");
  if (index < 0) bots.push({ ref, token: token!, enabled });
  else bots[index] = { ...bots[index], token: token || bots[index].token, enabled };
  return { ...config.values, token: "", bots };
}
