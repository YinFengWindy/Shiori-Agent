import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cx, inputClass } from "../shared/styles";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { buildProactiveTransportSequence, roleBindingChannelLabel } from "./roleChannelBindings";

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

type RoleProactiveSettingsPanelProps = {
  bindings: RoleChannelBinding[];
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Configures the delivery policy after role channels have been selected. */
export function RoleProactiveSettingsPanel({ bindings, roleForm, onUpdate }: RoleProactiveSettingsPanelProps) {
  const selectedBinding = bindings.find((binding) => binding.channel === roleForm.proactiveTargetChannel && binding.chat_id === roleForm.proactiveTargetChatId);
  const transportSequence = selectedBinding ? buildProactiveTransportSequence(bindings, roleForm.proactiveTargetChannel ?? "", roleForm.proactiveTargetChatId ?? "") : [];
  const updateNumber = (field: "proactiveAgentMaxSteps" | "proactiveAgentContentLimit" | "proactiveAgentWebFetchMaxChars" | "proactiveDriftMaxSteps" | "proactiveDriftMinIntervalHours", fallback: number) => (event: React.ChangeEvent<HTMLInputElement>) => onUpdate((current) => ({ ...current, [field]: parseNumber(event.target.value, fallback) }));

  return (
    <section className="grid gap-4 rounded-md border border-[#E5E7EB] bg-white p-5 text-sm text-[#1F2937] shadow-[0_12px_30px_rgba(15,23,42,0.06)]" data-testid="role-proactive-config">
      <div className="flex items-center justify-between gap-3"><div><h2 className="font-medium">主动推送</h2><p className="mt-1 text-xs text-[#6B7280]">定义该角色的优先投递位置和执行边界。</p></div><SettingsToggleCard checked={Boolean(roleForm.proactiveEnabled)} ariaLabel="主动推送" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveEnabled: checked }))} /></div>
      <label className="grid gap-1.5 text-xs"><span>首选渠道</span><select className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} value={`${roleForm.proactiveTargetChannel ?? ""}:${roleForm.proactiveTargetChatId ?? ""}`} onChange={(event) => { const selected = bindings.find((binding) => `${binding.channel}:${binding.chat_id}` === event.target.value); onUpdate((current) => ({ ...current, proactiveTargetChannel: selected?.channel ?? "", proactiveTargetChatId: selected?.chat_id ?? "" })); }}><option value=":">未选择</option>{bindings.filter((binding) => binding.chat_id.trim()).map((binding) => <option key={`${binding.channel}:${binding.chat_id}`} value={`${binding.channel}:${binding.chat_id}`}>{roleBindingChannelLabel(binding.channel)} · {binding.chat_id}</option>)}</select></label>
      <label className="grid gap-1.5 text-xs"><span>策略</span><select className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} value={roleForm.proactiveProfile ?? "daily"} onChange={(event) => onUpdate((current) => ({ ...current, proactiveProfile: event.target.value }))}><option value="daily">日常</option><option value="quiet">低打扰</option><option value="dev_verify">开发验证</option></select></label>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="grid gap-1.5 text-xs"><span>Agent 模型</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} value={roleForm.proactiveAgentModel ?? ""} placeholder="沿用全局 Agent 模型" onChange={(event) => onUpdate((current) => ({ ...current, proactiveAgentModel: event.target.value }))} /></label>
        <label className="grid gap-1.5 text-xs"><span>Agent 最大步数</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} inputMode="numeric" value={String(roleForm.proactiveAgentMaxSteps ?? 35)} onChange={updateNumber("proactiveAgentMaxSteps", roleForm.proactiveAgentMaxSteps ?? 35)} /></label>
        <label className="grid gap-1.5 text-xs"><span>候选内容数</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} inputMode="numeric" value={String(roleForm.proactiveAgentContentLimit ?? 5)} onChange={updateNumber("proactiveAgentContentLimit", roleForm.proactiveAgentContentLimit ?? 5)} /></label>
        <label className="grid gap-1.5 text-xs"><span>网页上下文字符数</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} inputMode="numeric" value={String(roleForm.proactiveAgentWebFetchMaxChars ?? 8000)} onChange={updateNumber("proactiveAgentWebFetchMaxChars", roleForm.proactiveAgentWebFetchMaxChars ?? 8000)} /></label>
      </div>
      <div className="flex items-center justify-between gap-3"><span>Drift</span><SettingsToggleCard checked={Boolean(roleForm.proactiveDriftEnabled)} ariaLabel="Drift" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveDriftEnabled: checked }))} /></div>
      <div className="grid gap-3 md:grid-cols-2"><label className="grid gap-1.5 text-xs"><span>Drift 最大步数</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} inputMode="numeric" value={String(roleForm.proactiveDriftMaxSteps ?? 20)} onChange={updateNumber("proactiveDriftMaxSteps", roleForm.proactiveDriftMaxSteps ?? 20)} /></label><label className="grid gap-1.5 text-xs"><span>Drift 最小间隔（小时）</span><input className={cx(inputClass, "border-[#D8DCE2] bg-white text-[#1F2937]")} inputMode="numeric" value={String(roleForm.proactiveDriftMinIntervalHours ?? 3)} onChange={updateNumber("proactiveDriftMinIntervalHours", roleForm.proactiveDriftMinIntervalHours ?? 3)} /></label></div>
      {transportSequence.length ? <ol className="grid gap-1.5 border-t border-[#E5E7EB] pt-4" data-testid="role-proactive-sequence">{transportSequence.map((binding, index) => <li className="flex min-w-0 items-center gap-2 text-xs" key={`${binding.channel}:${binding.chat_id}`}><span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[#EFF6FF] text-[#2563EB]">{index + 1}</span><span className="min-w-0 truncate">{roleBindingChannelLabel(binding.channel)} · {binding.chat_id}</span><span className="ml-auto shrink-0 text-[#6B7280]">{index === 0 ? "首选" : "无回复后尝试 · 5 分钟"}</span></li>)}</ol> : null}
    </section>
  );
}
