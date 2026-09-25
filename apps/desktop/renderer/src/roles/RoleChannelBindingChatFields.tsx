import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { cx } from "../shared/styles";
import type { RoleChannelBinding, RoleChatType } from "../shared/types";
import { Select } from "../shared/ui/Select";
import { composeRoleBindingChatId, findRoleChatType, roleBindingChatIdCopy, roleBindingNumber, roleChatTypeLabel, roleChatTypeOptions } from "./roleChatTypes";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";
import { RoleReadOnlyField, roleReadOnlyFieldClass } from "./RoleReadOnlyField";

type ChatTypeFieldProps = {
  binding: RoleChannelBinding;
  /** The binding's channel; null when no catalog row declares it (loading, or its plugin is gone). */
  channel: ChannelSummary | null;
  readOnly: boolean;
  onChange: (chatType: RoleChatType) => void;
};

/**
 * Session type picker. Read-only when the binding is locked, the channel
 * declares a single type, or no declaration is available (then the stored type shows).
 */
export function RoleChannelBindingChatTypeField({ binding, channel, readOnly, onChange }: ChatTypeFieldProps) {
  const pickable = !readOnly && channel !== null && channel.chatTypes.length > 1 ? channel : null;
  return (
    <div className={cx(roleFieldLabelClass, "min-w-0")}>
      <span className="flex min-h-5 items-center">类型</span>
      {pickable
        ? <Select aria-label="类型" className={roleFieldClass} value={binding.chat_type} onValueChange={(value) => {
            const next = pickable.chatTypes.find((item) => item.type === value);
            if (next) onChange(next.type);
          }} options={roleChatTypeOptions(pickable)} />
        : <RoleReadOnlyField label="类型">{roleChatTypeLabel(channel, binding.chat_type)}</RoleReadOnlyField>}
    </div>
  );
}

type ChatIdFieldProps = {
  binding: RoleChannelBinding;
  channel: ChannelSummary | null;
  readOnly: boolean;
  onChange: (chatId: string) => void;
};

/**
 * Number input for a binding: shows the number without the selected type's
 * prefix and writes the prefix back. Without a declared type (desktop, or a
 * binding whose plugin is gone) the stored chat id shows read-only.
 */
export function RoleChannelBindingChatIdField({ binding, channel, readOnly, onChange }: ChatIdFieldProps) {
  const chatType = findRoleChatType(channel, binding.chat_type);
  const copy = roleBindingChatIdCopy(chatType);
  const locked = readOnly || chatType === null;
  return (
    <label className={cx(roleFieldLabelClass, "min-w-0")}>
      <span className="flex min-h-5 items-center">{copy.label}</span>
      <input
        className={locked ? roleReadOnlyFieldClass : roleFieldClass}
        value={roleBindingNumber(binding.chat_id, chatType)}
        placeholder={copy.placeholder}
        readOnly={locked}
        onChange={(event) => onChange(composeRoleBindingChatId(event.target.value, chatType))}
      />
    </label>
  );
}
