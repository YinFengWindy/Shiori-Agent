import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { cx } from "../shared/styles";
import type { RoleChannelBinding } from "../shared/types";
import { StringListInput } from "../shared/ui/StringListInput";
import { roleBlockedSenderPlaceholder } from "./roleChannelCatalog";
import { roleFieldClass, roleFieldLabelClass, roleRowIconButtonClass } from "./roleEditorStyles";
import { RoleReadOnlyField } from "./RoleReadOnlyField";

const blocklistLabel = "黑名单";

type BlocklistFieldProps = {
  binding: RoleChannelBinding;
  /** The binding's channel; null when no catalog row declares it (loading, or its plugin is gone). */
  channel: ChannelSummary | null;
  readOnly: boolean;
  onChange: (blockedSenders: string[]) => void;
};

/**
 * Blacklist of a group binding: every member may talk to the role except the
 * listed IDs. A locked binding shows its entries without editing controls.
 */
export function RoleChannelBindingBlocklistField({ binding, channel, readOnly, onChange }: BlocklistFieldProps) {
  const lockedAndEmpty = readOnly && binding.blocked_senders.length === 0;
  return (
    <div className={cx(roleFieldLabelClass, "min-w-0")}>
      <span className="flex min-h-5 items-center">{blocklistLabel}</span>
      {lockedAndEmpty
        // Keeps the row's layout: a locked binding without entries still shows a read-only box.
        ? <RoleReadOnlyField label={blocklistLabel}>无</RoleReadOnlyField>
        : <StringListInput
            ariaLabel={blocklistLabel}
            items={binding.blocked_senders}
            onChange={onChange}
            inputClassName={roleFieldClass}
            addButtonClassName={roleRowIconButtonClass}
            placeholder={roleBlockedSenderPlaceholder(channel)}
            readOnly={readOnly}
          />}
    </div>
  );
}
