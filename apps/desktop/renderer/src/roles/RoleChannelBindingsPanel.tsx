import { Select } from "../shared/ui/Select";
import { Info, PlugsConnected, Plus, Trash, WarningCircle } from "@phosphor-icons/react";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { cx } from "../shared/styles";
import { roleFieldClass, roleFieldLabelClass, rolePanelGhostButtonClass, roleRowIconButtonClass } from "./roleEditorStyles";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
  isDesktopRoleBinding,
} from "./roleChannelBindings";
import {
  defaultRoleBindingChannel,
  roleBindingAvailability,
  roleBindingChannelOptions,
  roleChannelLabel,
  type RoleBindingAvailability,
  type RoleChannelCatalog,
} from "./roleChannelCatalog";
import { RoleChannelBindingBlocklistField } from "./RoleChannelBindingBlocklistField";
import { RoleChannelBindingChatIdField, RoleChannelBindingChatTypeField } from "./RoleChannelBindingChatFields";
import { RoleReadOnlyField } from "./RoleReadOnlyField";
import { changeRoleBindingChatType, isGroupChatType } from "./roleChatTypes";
import { RoleEditorSection } from "./RoleEditorSection";
import {
  createRoleBindingEntry,
  roleBindingEntries,
  splitRoleBindingEntries,
  updateRoleBindingEntry,
  type RoleBindingEntry,
} from "./roleProactiveCandidates";

type RoleChannelBindingsPanelProps = {
  activeRoleId: string;
  bindings: RoleChannelBinding[];
  /** `channels.list` rows; null while loading, which disables adding. */
  channels: RoleChannelCatalog;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
  /** Opens 设置 › 插件 on the providing plugin's own tab (null: the plugin list). */
  onOpenPluginSettings: (pluginId: string | null) => void;
};

type ChannelBindingRowProps = {
  activeRoleId: string;
  binding: RoleChannelBinding;
  channels: RoleChannelCatalog;
  onUpdate: (update: (binding: RoleChannelBinding) => RoleChannelBinding) => void;
  onRemove: () => void;
  onOpenPluginSettings: (pluginId: string | null) => void;
};

const noticeClass = "flex min-w-0 items-start gap-1.5 text-caption";
const noticeIconClass = "mt-px h-3.5 w-3.5 shrink-0";
const stateBadgeClass = "inline-flex shrink-0 items-center rounded-full px-2 py-px text-caption leading-4";

/** Explains why a binding cannot deliver yet, or why it became read-only. */
function ChannelBindingNotice({ availability, onOpenPluginSettings }: { availability: RoleBindingAvailability; onOpenPluginSettings: (pluginId: string | null) => void }) {
  if (availability.kind !== "editable") {
    return (
      <p className={cx(noticeClass, "text-ink-muted")}>
        <PlugsConnected className={noticeIconClass} weight="bold" aria-hidden="true" />
        {availability.kind === "missing" ? "提供该渠道的插件未安装" : "提供该渠道的插件已停用"}
      </p>
    );
  }
  const channel = availability.channel;
  if (channel?.state === "not_configured") {
    return (
      <p className={cx(noticeClass, "items-center text-ink-muted")}>
        <Info className={noticeIconClass} weight="bold" aria-hidden="true" />
        在
        <button
          className="rounded-sm font-medium text-accent-text underline-offset-2 hover:underline"
          data-testid="role-channel-open-plugin-settings"
          type="button"
          onClick={() => onOpenPluginSettings(channel.pluginId)}
        >
          设置 › 插件
        </button>
        中完成配置后生效
      </p>
    );
  }
  if (channel?.state === "failed") {
    return <p className={cx(noticeClass, "text-danger-text")} title={channel.error}><WarningCircle className={noticeIconClass} weight="bold" aria-hidden="true" /><span className="min-w-0 truncate">{channel.error || "渠道异常"}</span></p>;
  }
  return null;
}

/** Marks a channel whose binding cannot deliver right now. */
function ChannelStateBadge({ availability }: { availability: RoleBindingAvailability }) {
  if (availability.kind !== "editable") {
    return <span className={cx(stateBadgeClass, "border border-line bg-surface text-ink-muted")}>{availability.kind === "missing" ? "未安装" : "已停用"}</span>;
  }
  if (availability.channel?.state === "not_configured") return <span className={cx(stateBadgeClass, "bg-warning-soft text-warning-text")}>未配置</span>;
  if (availability.channel?.state === "failed") return <span className={cx(stateBadgeClass, "bg-danger-soft text-danger-text")}>异常</span>;
  return null;
}

/**
 * Renders one channel session of the role and its editable access boundary:
 * channel and session type on the first line, the number below, and for a
 * group the blacklist of members the role ignores. A binding
 * whose provider is disabled or gone keeps its data read-only; it can still be
 * removed.
 */
function ChannelBindingRow({ activeRoleId, binding, channels, onUpdate, onRemove, onOpenPluginSettings }: ChannelBindingRowProps) {
  const desktopBinding = isDesktopRoleBinding(binding);
  const availability = roleBindingAvailability(binding, channels);
  const readOnly = availability.kind !== "editable";
  const channel = availability.kind === "missing" ? null : availability.channel;
  const label = roleChannelLabel(binding.channel, channels);

  return (
    <div
      className={cx("grid grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-lg border p-4", readOnly ? "border-dashed border-line bg-surface-soft" : "border-line-soft bg-surface shadow-soft")}
      data-testid="role-channel-binding"
      data-availability={availability.kind}
    >
      <div className="grid min-w-0 gap-3">
        <div className="grid gap-3 sm:grid-cols-[168px_136px]">
          <div className={cx(roleFieldLabelClass, "min-w-0")}>
            <span className="flex min-h-5 items-center gap-1.5">渠道<ChannelStateBadge availability={availability} /></span>
            {readOnly
              ? <RoleReadOnlyField label="渠道">{label}</RoleReadOnlyField>
              : <Select aria-label="渠道" className={roleFieldClass} value={binding.channel} onValueChange={(value) => onUpdate((item) => changeRoleBindingChannel(item, value, activeRoleId, channels))} options={roleBindingChannelOptions(channels, binding.channel)} />}
          </div>
          {!desktopBinding
            ? <RoleChannelBindingChatTypeField binding={binding} channel={channel} readOnly={readOnly} onChange={(chatType) => onUpdate((item) => changeRoleBindingChatType(item, channel, chatType))} />
            : null}
        </div>
        <RoleChannelBindingChatIdField binding={binding} channel={channel} readOnly={desktopBinding || readOnly} onChange={(chatId) => onUpdate((item) => ({ ...item, chat_id: chatId }))} />
        {isGroupChatType(binding.chat_type)
          ? <RoleChannelBindingBlocklistField binding={binding} channel={channel} readOnly={readOnly} onChange={(blockedSenders) => onUpdate((item) => ({ ...item, blocked_senders: blockedSenders }))} />
          : null}
        <ChannelBindingNotice availability={availability} onOpenPluginSettings={onOpenPluginSettings} />
      </div>
      <div className="flex items-start pt-5 sm:pt-6">
        <button className={roleRowIconButtonClass} type="button" onClick={onRemove} aria-label={`移除${label}绑定`} title="移除"><Trash className="h-4 w-4 text-danger-text" weight="bold" /></button>
      </div>
    </div>
  );
}

/**
 * Edits the channel sessions owned by the role. Every edit carries each
 * binding's proactive candidate flag along, so candidates follow renames and
 * removals, and a new binding starts with its session type's default.
 */
export function RoleChannelBindingsPanel({ activeRoleId, bindings, channels, onUpdate, onOpenPluginSettings }: RoleChannelBindingsPanelProps) {
  function updateEntries(update: (entries: RoleBindingEntry[]) => RoleBindingEntry[]) {
    onUpdate((current) => ({
      ...current,
      ...splitRoleBindingEntries(update(roleBindingEntries(current.channelBindings ?? [], current.proactiveCandidates ?? []))),
    }));
  }

  return (
    <RoleEditorSection
      title="渠道绑定"
      data-testid="role-channel-config"
      action={<button className={rolePanelGhostButtonClass} type="button" disabled={channels === null} onClick={() => updateEntries((entries) => [...entries, createRoleBindingEntry(createRoleChannelBinding(activeRoleId, defaultRoleBindingChannel(channels), channels))])} aria-label="添加渠道绑定"><Plus className="h-4 w-4" weight="bold" />添加</button>}
    >
      {bindings.length
        ? <div className="grid gap-3">{bindings.map((binding, index) => (
            <ChannelBindingRow
              activeRoleId={activeRoleId}
              binding={binding}
              channels={channels}
              onUpdate={(update) => updateEntries((entries) => entries.map((entry, entryIndex) => entryIndex === index ? updateRoleBindingEntry(entry, update) : entry))}
              onRemove={() => updateEntries((entries) => entries.filter((_, entryIndex) => entryIndex !== index))}
              onOpenPluginSettings={onOpenPluginSettings}
              key={`${binding.channel}:${binding.chat_id}:${index}`}
            />
          ))}</div>
        : <div className="rounded-lg border border-dashed border-line bg-surface-soft py-8 text-center text-caption text-ink-muted">尚未绑定渠道</div>}
    </RoleEditorSection>
  );
}
