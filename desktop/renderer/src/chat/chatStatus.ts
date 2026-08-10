const beijingTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "Asia/Shanghai",
});

/** Formats an active loneliness cooldown for the chat status surface. */
export function formatLonelinessCooldownStatus(
  cooldownUntil: string,
  now: Date = new Date(),
) {
  const cooldown = new Date(cooldownUntil);
  if (!cooldownUntil || Number.isNaN(cooldown.getTime()) || cooldown <= now) {
    return "";
  }
  return `冷却至 ${beijingTimeFormatter.format(cooldown)}`;
}
