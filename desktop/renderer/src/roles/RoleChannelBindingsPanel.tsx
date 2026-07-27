import { ArrowDownIcon, ArrowUpIcon, DeleteIcon } from "../shared/icons";
import { cx, inputClass } from "../shared/styles";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
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

/** Edits the ordered channel destinations owned by the role. */
export function RoleChannelBindingsPanel({ activeRoleId, bindings, onUpdate }: RoleChannelBindingsPanelProps) {
  function updateBindings(update: (current: RoleChannelBinding[]) => RoleChannelBinding[]): void {
    onUpdate((current) => {
      const channelBindings = update(current.channelBindings ?? []);
      const targetStillBound = channelBindings.some((binding) => binding.channel === current.proactiveTargetChannel && binding.chat_id === current.proactiveTargetChatId);
      return {
        ...current,
        channelBindings,
        proactiveTargetChannel: targetStillBound ? current.proactiveTargetChannel : "",
        proactiveTargetChatId: targetStillBound ? current.proactiveTargetChatId : "",
      };
    });
  }

  return (
    <section className="grid gap-4 rounded-md border border-white/50 bg-white/75 p-5 text-sm text-[#302019] shadow-[0_12px_30px_rgba(40,20,10,0.08)]" data-testid="role-channel-config">
      <div className="flex items-center justify-between gap-3">
        <div><h2 className="font-medium">渠道绑定</h2><p className="mt-1 text-xs text-[#796d67]">按顺序维护角色可使用的会话与群组。</p></div>
        <button className="rounded-md border border-[#b99d8f] bg-white/80 px-3 py-1.5 text-xs transition hover:border-[#9c512f]" type="button" onClick={() => updateBindings((current) => [...current, createRoleChannelBinding(activeRoleId)])}>添加</button>
      </div>
      {bindings.length ? bindings.map((binding, index) => (
        <div className="grid gap-2 rounded-md border border-[#e5d6ce] bg-white/55 p-3" key={`${binding.channel}:${binding.chat_id}:${index}`}>
          <div className="grid gap-2 md:grid-cols-[120px_minmax(0,1fr)_auto_auto]">
            <select className={cx(inputClass, "border-[#d8c5ba] bg-white text-[#241914]")} value={binding.channel} onChange={(event) => updateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? changeRoleBindingChannel(item, event.target.value, activeRoleId) : item))}>
              <option value="telegram">Telegram</option><option value="qq">QQ</option><option value="qqbot">QQBot</option><option value="desktop">桌面端</option>
            </select>
            <input className={cx(inputClass, "border-[#d8c5ba] bg-white text-[#241914]")} value={binding.chat_id} placeholder="会话 / 群组 ID" readOnly={isDesktopRoleBinding(binding)} onChange={(event) => updateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, chat_id: event.target.value } : item))} />
            <div className="flex items-center justify-end gap-1">
              <button className="grid h-8 w-8 place-items-center rounded-md border border-[#d8c5ba] text-[#6c5a51] transition hover:border-[#9c512f] hover:text-[#9c512f] disabled:cursor-default disabled:opacity-35" type="button" onClick={() => updateBindings((current) => moveRoleChannelBinding(current, index, "up"))} disabled={index === 0} aria-label={`上移${roleBindingChannelLabel(binding.channel)}绑定`} title="上移"><ArrowUpIcon className="h-4 w-4 stroke-current" /></button>
              <button className="grid h-8 w-8 place-items-center rounded-md border border-[#d8c5ba] text-[#6c5a51] transition hover:border-[#9c512f] hover:text-[#9c512f] disabled:cursor-default disabled:opacity-35" type="button" onClick={() => updateBindings((current) => moveRoleChannelBinding(current, index, "down"))} disabled={index === bindings.length - 1} aria-label={`下移${roleBindingChannelLabel(binding.channel)}绑定`} title="下移"><ArrowDownIcon className="h-4 w-4 stroke-current" /></button>
            </div>
            <button className="grid h-8 w-8 place-items-center rounded-md border border-transparent text-[#9a3d2c] transition hover:border-[#e8c7c0] hover:text-[#702718]" type="button" onClick={() => updateBindings((current) => current.filter((_, itemIndex) => itemIndex !== index))} aria-label={`移除${roleBindingChannelLabel(binding.channel)}绑定`} title="移除"><DeleteIcon className="h-4 w-4 fill-current" /></button>
          </div>
          {!isDesktopRoleBinding(binding) ? <label className="grid gap-1.5 text-xs"><span>{roleBindingAllowFromLabel(binding.channel)}</span><input className={cx(inputClass, "border-[#d8c5ba] bg-white text-[#241914]")} value={binding.allow_from.join(", ")} onChange={(event) => updateBindings((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, allow_from: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } : item))} /></label> : null}
        </div>
      )) : <div className="rounded-md border border-dashed border-[#d8c5ba] px-4 py-6 text-center text-xs text-[#796d67]">尚未绑定渠道</div>}
    </section>
  );
}
