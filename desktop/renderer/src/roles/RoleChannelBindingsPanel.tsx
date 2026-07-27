import { CaretDown, CaretUp, ChatCircleDots, Plus, Trash } from "@phosphor-icons/react";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { roleDeliveryFieldClass, roleDeliveryIconButtonClass } from "./roleDeliveryStyles";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
  isDesktopRoleBinding,
  moveRoleChannelBinding,
  roleBindingAllowFromLabel,
  roleBindingChannelLabel,
} from "./roleChannelBindings";

type RoleChannelBindingsPanelProps = {
  activeRoleId: string;
  bindings: RoleChannelBinding[];
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

type ChannelBindingRowProps = {
  activeRoleId: string;
  binding: RoleChannelBinding;
  index: number;
  bindingsCount: number;
  onUpdateBindings: (update: (current: RoleChannelBinding[]) => RoleChannelBinding[]) => void;
};

/** Renders one ordered delivery destination and its editable access boundary. */
function ChannelBindingRow({ activeRoleId, binding, index, bindingsCount, onUpdateBindings }: ChannelBindingRowProps) {
  const desktopBinding = isDesktopRoleBinding(binding);

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] gap-3 border-b border-[#E7ECF1] py-4 first:pt-0 last:border-b-0 last:pb-0">
      <span className="grid h-8 w-8 place-items-center rounded-md bg-[#F3F6FA] text-xs font-medium text-[#52606D]" aria-label={`投递顺序 ${index + 1}`}>{index + 1}</span>
      <div className="grid min-w-0 gap-3">
        <div className="grid gap-3 sm:grid-cols-[132px_minmax(0,1fr)]">
          <label className="grid gap-1.5 text-xs text-[#667085]"><span>渠道</span><select className={roleDeliveryFieldClass} value={binding.channel} onChange={(event) => onUpdateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? changeRoleBindingChannel(item, event.target.value, activeRoleId) : item))}><option value="telegram">Telegram</option><option value="qq">QQ</option><option value="qqbot">QQBot</option><option value="desktop">桌面端</option></select></label>
          <label className="grid min-w-0 gap-1.5 text-xs text-[#667085]"><span>会话 / 群组 ID</span><input className={roleDeliveryFieldClass} value={binding.chat_id} placeholder="输入会话或群组 ID" readOnly={desktopBinding} onChange={(event) => onUpdateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, chat_id: event.target.value } : item))} /></label>
        </div>
        {!desktopBinding ? <label className="grid gap-1.5 text-xs text-[#667085]"><span>{roleBindingAllowFromLabel(binding.channel)}</span><input className={roleDeliveryFieldClass} value={binding.allow_from[0] ?? ""} placeholder="输入唯一联系人 ID" onChange={(event) => onUpdateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, allow_from: event.target.value.trim() ? [event.target.value.trim()] : [] } : item))} /></label> : <p className="text-xs text-[#7B8794]">{roleBindingChannelLabel(binding.channel)}使用当前角色的桌面对话。</p>}
      </div>
      <div className="flex items-start gap-0.5 pt-5 sm:pt-6">
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => moveRoleChannelBinding(current, index, "up"))} disabled={index === 0} aria-label={`上移${roleBindingChannelLabel(binding.channel)}绑定`} title="上移"><CaretUp className="h-4 w-4" weight="bold" /></button>
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => moveRoleChannelBinding(current, index, "down"))} disabled={index === bindingsCount - 1} aria-label={`下移${roleBindingChannelLabel(binding.channel)}绑定`} title="下移"><CaretDown className="h-4 w-4" weight="bold" /></button>
        <button className={roleDeliveryIconButtonClass} type="button" onClick={() => onUpdateBindings((current) => current.filter((_, itemIndex) => itemIndex !== index))} aria-label={`移除${roleBindingChannelLabel(binding.channel)}绑定`} title="移除"><Trash className="h-4 w-4 text-[#B54747]" weight="bold" /></button>
      </div>
    </div>
  );
}

/** Edits the ordered channel destinations owned by the role. */
export function RoleChannelBindingsPanel({ activeRoleId, bindings, onUpdate }: RoleChannelBindingsPanelProps) {
  function updateBindings(update: (current: RoleChannelBinding[]) => RoleChannelBinding[]): void {
    onUpdate((current) => {
      const channelBindings = update(current.channelBindings ?? []);
      const targetStillBound = channelBindings.some((binding) => binding.channel === current.proactiveTargetChannel && binding.chat_id === current.proactiveTargetChatId);
      return { ...current, channelBindings, proactiveTargetChannel: targetStillBound ? current.proactiveTargetChannel : "", proactiveTargetChatId: targetStillBound ? current.proactiveTargetChatId : "" };
    });
  }

  return (
    <section className="grid gap-5 text-sm text-[#1F2937]" data-testid="role-channel-config">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-md bg-[#F3F6FA] text-[#4B6B88]" aria-hidden="true"><ChatCircleDots className="h-5 w-5" weight="duotone" /></span><div><h2 className="text-sm font-semibold text-[#182230]">渠道绑定</h2><p className="mt-1 text-xs text-[#7B8794]">{bindings.length ? `已配置 ${bindings.length} 个投递位置，可调整回退顺序。` : "维护角色可使用的会话与群组。"}</p></div></div>
        <button className="grid h-9 w-9 place-items-center rounded-md text-[#52606D] transition hover:bg-[#F3F6FA] hover:text-[#182230] focus:outline-none focus:ring-2 focus:ring-primary/20" type="button" onClick={() => updateBindings((current) => [...current, createRoleChannelBinding(activeRoleId)])} aria-label="添加渠道绑定" title="添加渠道绑定"><Plus className="h-5 w-5" weight="bold" /></button>
      </div>
      {bindings.length ? <div>{bindings.map((binding, index) => <ChannelBindingRow activeRoleId={activeRoleId} binding={binding} index={index} bindingsCount={bindings.length} onUpdateBindings={updateBindings} key={`${binding.channel}:${binding.chat_id}:${index}`} />)}</div> : <div className="border-y border-dashed border-[#DDE5EC] py-6 text-center text-xs text-[#7B8794]">尚未绑定渠道</div>}
    </section>
  );
}
