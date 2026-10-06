import { useState } from "react";
import { ghostButtonClass, inputClass, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { GptSoVitsSettings } from "../shared/contracts";
import { usePrivateDraft } from "./usePrivateDraft";
import { useServiceHealth } from "./useServiceHealth";

/** Edits provider-owned service paths and distinguishes reachability from model verification. */
export function GptSoVitsSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const health = useServiceHealth(client);
  const state = usePrivateDraft(client, "settings", {
    load: () => client.call<GptSoVitsSettings>("settings.get"),
    save: async (value) => { const result = await client.call<GptSoVitsSettings>("settings.set", value); health.clear(); return result; },
  });
  const [confirmRestart, setConfirmRestart] = useState(false);
  const draft = state.draft;
  return <div className="grid gap-4">
    {state.error ? <host.ui.InlineError message={state.error} /> : null}
    {health.error ? <host.ui.InlineError message={health.error} /> : null}
    {state.loading ? <span className="text-ink-muted">正在读取设置…</span> : null}
    {draft ? <>
      <span className="text-body-sm text-ink-muted">配置版本：v2ProPlus</span>
      {([
        ["url", "服务地址"], ["gpt_weights", "GPT 权重路径"], ["sovits_weights", "SoVITS 权重路径"],
      ] as const).map(([field, label]) => <label key={field} className="grid gap-2">{label}<input aria-label={label} className={inputClass} disabled={state.saving} value={draft[field]} onChange={(event) => state.setDraft({ ...draft, [field]: event.target.value })} /></label>)}
      <div className="flex flex-wrap gap-2">
        <button className={ghostButtonClass} disabled={state.saving || !state.dirty} onClick={() => void state.save()}>保存</button>
        <button className={ghostButtonClass} disabled={state.saving || state.dirty || health.busy} onClick={() => void health.check()}>检查连接</button>
      </div>
    </> : null}
    {health.health ? <div className="grid gap-2 text-body-sm text-ink-secondary" role="status">
      <span>{health.health.reachable ? "服务可达" : "服务不可达"} · {health.health.busy ? "正在推理" : "空闲"}</span>
      <span>模型身份未验证 · 配置版本 {health.health.configured_version}</span>
      {health.health.recovery_required ? <>
        <host.ui.InlineError message="上次推理结果不明，请先重启外部服务。" />
        <div><button className={ghostButtonClass} disabled={health.busy || state.dirty || state.saving} onClick={() => setConfirmRestart(true)}>我已重启服务</button></div>
      </> : null}
    </div> : null}
    <host.ui.ConfirmDialog open={confirmRestart} title="确认外部服务已重启？" description="仅在已手动重启 GPT-SoVITS 服务后继续。" confirmLabel="确认已重启" destructive={false} persona={true} onClose={() => setConfirmRestart(false)} onConfirm={() => { setConfirmRestart(false); void health.check(true); }} />
  </div>;
}
