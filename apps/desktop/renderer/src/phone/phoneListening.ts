import { phoneSeparatorTime } from "./phoneChatPresentation";
import type { PhoneListeningToggle } from "./phoneListeningClient";

/**
 * A daily cap typed into a field: a whole number of at least 1 is that
 * cap, a blank field is none (null: the default applies); anything else
 * is invalid (undefined).
 */
export function parseDailyCap(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return /^\d+$/.test(trimmed) && Number(trimmed) >= 1 ? Number(trimmed) : undefined;
}

/** A cap draft would store something other than `stored` (compared as parsed). */
export function dailyCapDraftDirty(draft: string, stored: string) {
  return parseDailyCap(draft) !== parseDailyCap(stored);
}

/**
 * The 旁听 block's switch log, newest first: who changed it (「我」 for
 * the user, the role's name for the role), to on or off, and when.
 */
export function phoneListeningToggleRows(toggles: readonly PhoneListeningToggle[], roleName: string, now: Date) {
  return toggles.map((toggle, index) => ({
    key: `${index}:${toggle.at}`,
    who: toggle.operator === "user" ? "我" : roleName,
    action: toggle.enabled ? "开启" : "关闭",
    time: phoneSeparatorTime(toggle.at, now),
  }));
}
