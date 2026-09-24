import { Select } from "../shared/ui/Select";
import { CaretDown, PaperPlaneTilt, SlidersHorizontal } from "@phosphor-icons/react";
import type React from "react";
import { useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { roleDeliveryFieldClass } from "./roleDeliveryStyles";
import { buildProactiveTransportSequence } from "./roleChannelBindings";
import { roleChannelLabel, type RoleChannelCatalog } from "./roleChannelCatalog";
import { roleProactiveDefaults } from "./roleProactiveDefaults";

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

type RoleProactiveSettingsPanelProps = {
  bindings: RoleChannelBinding[];
  /** Supplies channel display labels; null while `channels.list` loads. */
  channels: RoleChannelCatalog;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Configures the delivery policy after role channels have been selected. */
export function RoleProactiveSettingsPanel({ bindings, channels, roleForm, onUpdate }: RoleProactiveSettingsPanelProps) {
  const [executionOpen, setExecutionOpen] = useState(false);
  const selectedBinding = bindings.find((binding) => binding.channel === roleForm.proactiveTargetChannel && binding.chat_id === roleForm.proactiveTargetChatId);
  const transportSequence = selectedBinding ? buildProactiveTransportSequence(bindings, roleForm.proactiveTargetChannel ?? "", roleForm.proactiveTargetChatId ?? "") : [];
  const usableBindings = bindings.filter((binding) => binding.chat_id.trim());
  const updateNumber = (field: "proactiveAgentMaxSteps" | "proactiveAgentContentLimit" | "proactiveAgentWebFetchMaxChars" | "proactiveDriftMaxSteps" | "proactiveDriftMinIntervalHours", fallback: number) => (event: React.ChangeEvent<HTMLInputElement>) => onUpdate((current) => ({ ...current, [field]: parseNumber(event.target.value, fallback) }));

  return (
    <section className="grid gap-5 rounded-2xl bg-[#EFF6F2] p-5 text-sm text-ink" data-testid="role-proactive-config">
      <div className="flex items-start justify-between gap-4"><div className="flex min-w-0 items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/75 text-[#2E7D5B]" aria-hidden="true"><PaperPlaneTilt className="h-5 w-5" weight="duotone" /></span><div><h2 className="text-sm font-semibold text-ink">主动推送</h2><p className="mt-1 text-xs text-ink-muted">{roleForm.proactiveEnabled ? "角色会按设定的位置和策略主动投递。" : "启用后角色可在合适时机主动联系。"}</p></div></div><div className="flex shrink-0 items-center gap-3"><span className={roleForm.proactiveEnabled ? "text-xs text-success-text" : "text-xs text-ink-muted"}>{roleForm.proactiveEnabled ? "已启用" : "未启用"}</span><SettingsToggleCard checked={Boolean(roleForm.proactiveEnabled ?? roleProactiveDefaults.enabled)} ariaLabel="主动推送" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveEnabled: checked }))} /></div></div>
      <div className="grid gap-4 border-y border-[#DCEAE2] py-4 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-ink-muted"><span>首选投递位置</span><Select aria-label="首选投递位置" className={roleDeliveryFieldClass} value={`${roleForm.proactiveTargetChannel ?? roleProactiveDefaults.targetChannel}:${roleForm.proactiveTargetChatId ?? roleProactiveDefaults.targetChatId}`} onValueChange={(value) => { const selected = bindings.find((binding) => `${binding.channel}:${binding.chat_id}` === value); onUpdate((current) => ({ ...current, proactiveTargetChannel: selected?.channel ?? roleProactiveDefaults.targetChannel, proactiveTargetChatId: selected?.chat_id ?? roleProactiveDefaults.targetChatId })); }} options={[{ value: ":", label: "未选择" }, ...usableBindings.map((binding) => ({ value: `${binding.channel}:${binding.chat_id}`, label: roleChannelLabel(binding.channel, channels) + " · " + binding.chat_id }))]}/></label><label className="grid gap-1.5 text-xs text-ink-muted"><span>推送策略</span><Select aria-label="推送策略" className={roleDeliveryFieldClass} value={roleForm.proactiveProfile ?? roleProactiveDefaults.profile} onValueChange={(value) => onUpdate((current) => ({ ...current, proactiveProfile: value }))} options={[{ value: "daily", label: "日常" }, { value: "quiet", label: "低打扰" }, { value: "dev_verify", label: "开发验证" }]} /></label></div>
      {transportSequence.length ? <ol className="grid gap-2" data-testid="role-proactive-sequence">{transportSequence.map((binding, index) => <li className="flex min-w-0 items-center gap-3 border-b border-[#E2EEE7] py-2.5 last:border-b-0" key={`${binding.channel}:${binding.chat_id}`}><span className={index === 0 ? "grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white text-xs font-medium text-success-text" : "grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/60 text-xs text-ink-muted"}>{index + 1}</span><span className="min-w-0 truncate text-sm text-ink-secondary">{roleChannelLabel(binding.channel, channels)} · {binding.chat_id}</span><span className="ml-auto shrink-0 text-xs text-ink-muted">{index === 0 ? "首选" : "无回复后尝试"}</span></li>)}</ol> : <p className="text-xs text-ink-muted">先在上方绑定渠道，再选择主动投递位置。</p>}
      <div><button className="flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-ink-secondary transition hover:bg-white/70 hover:text-ink focus:outline-none" type="button" aria-expanded={executionOpen} onClick={() => setExecutionOpen((current) => !current)}><SlidersHorizontal className="h-4 w-4" weight="bold" />执行参数<CaretDown className={executionOpen ? "h-4 w-4 rotate-180 transition-transform" : "h-4 w-4 transition-transform"} weight="bold" /></button>{executionOpen ? <div className="grid gap-4 border-t border-[#DCEAE2] pt-4"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-ink-muted"><span>Agent 最大步数</span><input className={roleDeliveryFieldClass} inputMode="numeric" value={String(roleForm.proactiveAgentMaxSteps ?? roleProactiveDefaults.agentMaxSteps)} onChange={updateNumber("proactiveAgentMaxSteps", roleProactiveDefaults.agentMaxSteps)} /></label><label className="grid gap-1.5 text-xs text-ink-muted"><span>候选内容数</span><input className={roleDeliveryFieldClass} inputMode="numeric" value={String(roleForm.proactiveAgentContentLimit ?? roleProactiveDefaults.agentContentLimit)} onChange={updateNumber("proactiveAgentContentLimit", roleProactiveDefaults.agentContentLimit)} /></label><label className="grid gap-1.5 text-xs text-ink-muted"><span>网页上下文字符数</span><input className={roleDeliveryFieldClass} inputMode="numeric" value={String(roleForm.proactiveAgentWebFetchMaxChars ?? roleProactiveDefaults.agentWebFetchMaxChars)} onChange={updateNumber("proactiveAgentWebFetchMaxChars", roleProactiveDefaults.agentWebFetchMaxChars)} /></label></div><div className="grid gap-4 border-t border-[#E2EEE7] pt-4"><div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-medium text-ink">Drift</h3><p className="mt-1 text-xs text-ink-muted">控制角色对关系状态的主动漂移节奏。</p></div><SettingsToggleCard checked={Boolean(roleForm.proactiveDriftEnabled ?? roleProactiveDefaults.driftEnabled)} ariaLabel="Drift" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveDriftEnabled: checked }))} /></div><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-xs text-ink-muted"><span>Drift 最大步数</span><input className={roleDeliveryFieldClass} inputMode="numeric" value={String(roleForm.proactiveDriftMaxSteps ?? roleProactiveDefaults.driftMaxSteps)} onChange={updateNumber("proactiveDriftMaxSteps", roleProactiveDefaults.driftMaxSteps)} /></label><label className="grid gap-1.5 text-xs text-ink-muted"><span>Drift 最小间隔（小时）</span><input className={roleDeliveryFieldClass} inputMode="numeric" value={String(roleForm.proactiveDriftMinIntervalHours ?? roleProactiveDefaults.driftMinIntervalHours)} onChange={updateNumber("proactiveDriftMinIntervalHours", roleProactiveDefaults.driftMinIntervalHours)} /></label></div></div></div> : null}</div>
    </section>
  );
}
