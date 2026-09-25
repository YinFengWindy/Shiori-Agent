import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { cx } from "../shared/styles";
import type { RoleChannelBinding, RoleChatType } from "../shared/types";
import { Select } from "../shared/ui/Select";
import { roleBindingChatIdCopy } from "./roleChannelCatalog";
import { composeRoleBindingChatId, findRoleChatType, roleBindingNumber, roleChatTypeOptions } from "./roleChatTypes";
import { roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";

const lockedFieldClass = cx(roleFieldClass, "cursor-default text-ink-muted");

type ChatTypeFieldProps = {
  binding: RoleChannelBinding;
  /** A channel that declares at least one session type. */
  channel: ChannelSummary;
  readOnly: boolean;
  onChange: (chatType: RoleChatType) => void;
};

/** Session type picker; read-only when the binding is locked or the channel declares a single type. */
export function RoleChannelBindingChatTypeField({ binding, channel, readOnly, onChange }: ChatTypeFieldProps) {
  const locked = readOnly || channel.chatTypes.length === 1;
  return (
    <div className={cx(roleFieldLabelClass, "min-w-0")}>
      <span className="flex min-h-5 items-center">类型</span>
      {locked
        ? <span className={cx(lockedFieldClass, "truncate")} role="textbox" aria-label="类型" aria-readonly="true">{findRoleChatType(channel, binding.chat_type)?.label ?? binding.chat_type}</span>
        : <Select aria-label="类型" className={roleFieldClass} value={binding.chat_type} onValueChange={(value) => {
            const next = channel.chatTypes.find((item) => item.type === value);
            if (next) onChange(next.type);
          }} options={roleChatTypeOptions(channel)} />}
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
 * Number input for a binding. With a declared session type it shows the number
 * only and writes back the type's prefix; otherwise it edits the raw chat id.
 */
export function RoleChannelBindingChatIdField({ binding, channel, readOnly, onChange }: ChatIdFieldProps) {
  const chatType = findRoleChatType(channel, binding.chat_type);
  const copy = roleBindingChatIdCopy(channel, chatType);
  return (
    <label className={cx(roleFieldLabelClass, "min-w-0")}>
      <span className="flex min-h-5 items-center">{copy.label}</span>
      <input
        className={readOnly ? lockedFieldClass : roleFieldClass}
        value={roleBindingNumber(binding.chat_id, chatType)}
        placeholder={copy.placeholder}
        readOnly={readOnly}
        onChange={(event) => onChange(composeRoleBindingChatId(event.target.value, chatType))}
      />
    </label>
  );
}
