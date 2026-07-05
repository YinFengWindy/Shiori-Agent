import type { SettingsFormData } from "../shared/types";

export type BindingChatIdMeta = {
  label: string;
  placeholder: string;
  hint: string;
};

/** Joins textarea-backed list values into the newline format used by the settings inputs. */
export function joinLines(values: string[]): string {
  return values.join("\n");
}

/** Splits newline textarea content into trimmed non-empty rows. */
export function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Deep-clones settings draft data so nested updates keep the current save semantics intact. */
export function cloneSettings(data: SettingsFormData): SettingsFormData {
  return JSON.parse(JSON.stringify(data)) as SettingsFormData;
}

/** Parses launcher command rows from the peer-agent textarea. */
export function parseLauncher(value: string): string[] {
  return splitLines(value);
}

/** Formats launcher command rows back into a textarea value. */
export function formatLauncher(values: string[]): string {
  return values.join("\n");
}

/** Compares settings snapshots using the same serialized structure used for save/reset. */
export function settingsEqual(left: SettingsFormData | null, right: SettingsFormData | null): boolean {
  if (!left || !right) return false;
  return JSON.stringify(left) === JSON.stringify(right);
}

/** Parses a numeric text field while preserving the previous numeric value on invalid input. */
export function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Describes how a transport-specific binding chat id field should be labeled and explained. */
export function getBindingChatIdMeta(channel: string): BindingChatIdMeta {
  switch (channel) {
    case "desktop":
      return {
        label: "Desktop Session",
        placeholder: "自动使用 role:<role_id>",
        hint: "桌面端会把主动消息直接写入该角色会话，不需要手填 chat_id。",
      };
    case "telegram":
      return {
        label: "Telegram Chat ID",
        placeholder: "例如 123456789",
        hint: "通常填 Telegram user id 或群 chat_id。",
      };
    case "qq":
      return {
        label: "QQ Chat ID",
        placeholder: "例如好友 QQ 号或群号",
        hint: "和运行时 transport 使用的 chat_id 保持一致。",
      };
    case "qqbot":
      return {
        label: "QQBot Chat ID",
        placeholder: "例如 c2c:USER_OPENID",
        hint: "私聊常用 c2c:USER_OPENID；如果后续支持群，再填对应 group 标识。",
      };
    case "feishu":
      return {
        label: "Feishu Chat ID",
        placeholder: "例如 open_id / chat_id",
        hint: "填入运行时实际使用的 open_id 或 chat_id。",
      };
    case "cli":
      return {
        label: "CLI Session Key",
        placeholder: "例如 local 或 cli:local",
        hint: "用于把特定 CLI 会话固定路由到某个角色。",
      };
    default:
      return {
        label: "Chat ID",
        placeholder: "输入 transport chat_id",
        hint: "填入该渠道实际使用的 chat_id。",
      };
  }
}

/** Provides the memory engine options, adding a custom current value when needed. */
export function getMemoryEngineOptions(currentValue: string): Array<{ value: string; label: string }> {
  const normalized = currentValue.trim();
  const options = [
    { value: "", label: "default" },
  ];
  if (normalized && normalized !== "default") {
    options.push({ value: normalized, label: normalized });
  }
  return options;
}
