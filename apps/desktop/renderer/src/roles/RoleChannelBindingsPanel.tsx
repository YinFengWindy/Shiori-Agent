import { Select } from "../shared/ui/Select";
import { CaretDown, CaretUp, ChatCircleDots, Info, PlugsConnected, Plus, Trash, WarningCircle } from "@phosphor-icons/react";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { cx } from "../shared/styles";
import { roleDeliveryFieldClass, roleDeliveryIconButtonClass } from "./roleDeliveryStyles";
import { rolePanelGhostButtonClass } from "./roleEditorStyles";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
  isDesktopRoleBinding,
  moveRoleChannelBinding,
} from "./roleChannelBindings";
import {
  defaultRoleBindingChannel,
  roleBindingAvailability,
  roleBindingChannelOptions,
  roleBindingChatIdCopy,
  roleBindingContactLabel,
  roleChannelLabel,
  roleChannelSettingsLocation,
  type RoleBindingAvailability,
  type RoleChannelCatalog,
} from "./roleChannelCatalog";

type RoleChannelBindingsPanelProps = {
  activeRoleId: string;
  bindings: RoleChannelBinding[];
  /** `channels.list` rows; null while loading, which disables adding. */
  channels: RoleChannelCatalog;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

type ChannelBindingRowProps = {
  activeRoleId: string;
  binding: RoleChannelBinding;
  channels: RoleChannelCatalog;
  index: number;
  bindingsCount: number;
  onUpdateBindings: (update: (current: RoleChannelBinding[]) => RoleChannelBinding[]) => void;
};

const noticeClass = "flex min-w-0 items-start gap-1.5 text-xs";
const noticeIconClass = "mt-px h-3.5 w-3.5 shrink-0";
const stateBadgeClass = "inline-flex shrink-0 items-center rounded-full px-2 py-px text-[11px] leading-4";

/** Explains why a binding cannot deliver yet, or why it became read-only. */
function ChannelBindingNotice({ availability }: { availability: RoleBindingAvailability }) {
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
    return <p className={cx(noticeClass, "text-ink-muted")}><Info className={noticeIconClass} weight="bold" aria-hidden="true" />在 {roleChannelSettingsLocation(channel)} 中完成配置后生效</p>;
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
 * Renders one ordered delivery destination and its editable access boundary.
 * A binding whose provider is disabled or gone keeps its data read-only; it
 * can still be reordered or removed.
 */
function ChannelBindingRow({ activeRoleId, binding, channels, index, bindingsCount, onUpdateBindings }: ChannelBindingRowProps) {
  const desktopBinding = isDesktopRoleBinding(binding);
  const availability = roleBindingAvailability(binding, channels);
  const readOnly = availability.kind !== "editable";
  const channel = availability.kind === "missing" ? null : availability.channel;
  const label = roleChannelLabel(binding.channel, channels);
  const chatIdCopy = roleBindingChatIdCopy(channel);
  const readOnlyFieldClass = cx(roleDeliveryFieldClass, readOnly && "cursor-default text-ink-muted");
  const updateThis = (update: (item: RoleChannelBinding) => RoleChannelBinding) =>
    onUpdateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? update(item) : item));

  return (
    <div className={cx("grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 rounded-lg p-4", readOnly ? "border border-dashed border-line bg-surface-soft" : "bg-lavender-soft")} data-testid="role-channel-binding" data-availability={availability.kind}>
      <span className="grid h-8 w-8 place-items-center rounded-md bg-white/75 text-xs font-medium text-lavender-text" aria-label={`投递顺序 ${index + 1}`}>{index + 1}</span>
      <div className="grid min-w-0 gap-3">
        <div className="grid gap-3 sm:grid-cols-[168px_minmax(0,1fr)]">
          <div className="grid min-w-0 gap-1.5 text-xs text-ink-muted">
            <span className="flex min-h-5 items-center gap-1.5">渠道<ChannelStateBadge availability={availability} /></span>
            {readOnly
              ? <span className={cx(readOnlyFieldClass, "truncate")} role="textbox" aria-label="渠道" aria-readonly="true">{label}</span>
              : <Select aria-label="渠道" className={roleDeliveryFieldClass} value={binding.channel} onValueChange={(value) => updateThis((item) => changeRoleBindingChannel(item, value, activeRoleId))} options={roleBindingChannelOptions(channels, binding.channel)} />}
          </div>
          <label className="grid min-w-0 gap-1.5 text-xs text-ink-muted"><span className="flex min-h-5 items-center">{chatIdCopy.label}</span><input className={readOnlyFieldClass} value={binding.chat_id} placeholder={chatIdCopy.placeholder} readOnly={desktopBinding || readOnly} onChange={(event) => updateThis((item) => ({ ...item, chat_id: event.target.value }))} /></label>
        </div>
        {!desktopBinding
          ? <label className="grid gap-1.5 text-xs text-ink-muted"><span>{roleBindingContactLabel(channel)}</span><input className={readOnlyFieldClass} value={binding.allow_from[0] ?? ""} placeholder="输入唯一联系人 ID" readOnly={readOnly} onChange={(event) => updateThis((item) => ({ ...item, allow_from: event.target.value.trim() ? [event.target.value.trim()] : [] }))} /></label>
          : <p className="text-xs text-ink-muted">{label}使用当前角色的桌面对话。</p>}
        <ChannelBindingNotice availability={availability} />
      </div>
      <div className="flex items-start gap-0.5 pt-5 sm:pt-6">
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => moveRoleChannelBinding(current, index, "up"))} disabled={index === 0} aria-label={`上移${label}绑定`} title="上移"><CaretUp className="h-4 w-4" weight="bold" /></button>
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => moveRoleChannelBinding(current, index, "down"))} disabled={index === bindingsCount - 1} aria-label={`下移${label}绑定`} title="下移"><CaretDown className="h-4 w-4" weight="bold" /></button>
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => current.filter((_, itemIndex) => itemIndex !== index))} aria-label={`移除${label}绑定`} title="移除"><Trash className="h-4 w-4 text-danger-text" weight="bold" /></button>
      </div>
    </div>
  );
}

/** Edits the ordered channel destinations owned by the role. */
export function RoleChannelBindingsPanel({ activeRoleId, bindings, channels, onUpdate }: RoleChannelBindingsPanelProps) {
  function updateBindings(update: (current: RoleChannelBinding[]) => RoleChannelBinding[]): void {
    onUpdate((current) => {
      const channelBindings = update(current.channelBindings ?? []);
      const targetStillBound = channelBindings.some((binding) => binding.channel === current.proactiveTargetChannel && binding.chat_id === current.proactiveTargetChatId);
      return { ...current, channelBindings, proactiveTargetChannel: targetStillBound ? current.proactiveTargetChannel : "", proactiveTargetChatId: targetStillBound ? current.proactiveTargetChatId : "" };
    });
  }

  return (
    <section className="grid gap-5 text-sm text-ink" data-testid="role-channel-config">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-lg bg-lavender-soft text-lavender-text" aria-hidden="true"><ChatCircleDots className="h-5 w-5" weight="duotone" /></span><div><h2 className="text-sm font-semibold text-ink">渠道绑定</h2><p className="mt-1 text-xs text-ink-muted">{bindings.length ? `已配置 ${bindings.length} 个投递位置，可调整回退顺序。` : "维护角色可使用的会话与群组。"}</p></div></div>
        <button className={rolePanelGhostButtonClass} type="button" disabled={channels === null} onClick={() => updateBindings((current) => [...current, createRoleChannelBinding(activeRoleId, defaultRoleBindingChannel(channels))])} aria-label="添加渠道绑定" title="添加渠道绑定"><Plus className="h-4 w-4" weight="bold" />添加</button>
      </div>
      {bindings.length ? <div className="grid gap-3">{bindings.map((binding, index) => <ChannelBindingRow activeRoleId={activeRoleId} binding={binding} channels={channels} index={index} bindingsCount={bindings.length} onUpdateBindings={updateBindings} key={`${binding.channel}:${binding.chat_id}:${index}`} />)}</div> : <div className="rounded-lg border border-dashed border-line bg-surface-soft py-8 text-center text-xs text-ink-muted">尚未绑定渠道</div>}
    </section>
  );
}
