import type { PluginConfigSnapshot } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";

/** One Bot credential stored only in Telegram's plugin configuration, with the role owning it. */
export type TelegramBotEntry = { ref: string; token: string; enabled: boolean; role_id?: string };

/** The Bots saved in the plugin configuration; the old single Token is not one of them. */
export function telegramBots(config: PluginConfigSnapshot): TelegramBotEntry[] {
  const values = config.values;
  return Array.isArray(values.bots) ? values.bots.flatMap((item) => {
    if (!item || typeof item !== "object" || !("ref" in item) || !("token" in item)) return [];
    if (typeof item.ref !== "string" || typeof item.token !== "string") return [];
    const roleId = "role_id" in item && typeof item.role_id === "string" && item.role_id ? { role_id: item.role_id } : {};
    return [{ ref: item.ref, token: item.token, enabled: !("enabled" in item) || item.enabled !== false, ...roleId }];
  }) : [];
}

/**
 * Build an explicit config update while preserving unrelated Bot credentials.
 * A new Bot belongs to `roleId`, the role it is saved from. A saved Bot is
 * only ever changed for its own role; one saved without an owner is never taken over.
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
    if (bots[index].role_id !== roleId) {
      throw new Error(bots[index].role_id ? "这个 Bot 已属于另一个角色" : "这个 Bot 是未归属的旧数据，请先手动清理");
    }
    bots[index] = { ...bots[index], token: token || bots[index].token, enabled };
  }
  // The whole table is written back; other fields, like the old single Token, stay as saved.
  const values: Record<string, unknown> = { ...config.values, bots };
  return values;
}
