import { ghostButtonClass, inputClass, usePrivateDraft, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { SenseVoiceSettings } from "./contract";
import { TranscriptionTest } from "./TranscriptionTest";
import { useServiceHealth } from "./useServiceHealth";

/** Owns SenseVoice connection edits and reports actual service readiness. */
export function SenseVoiceSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const state = usePrivateDraft(client, "settings", {
    load: () => client.call<SenseVoiceSettings>("settings.get"),
    save: (value) => client.call<SenseVoiceSettings>("settings.set", value),
  });
  const connection = useServiceHealth(client, state.saved);
  const draft = state.draft;
  const blocked = connection.busy || state.saving;
  return <div className="grid gap-6">
    {state.error ? <host.ui.InlineError message={state.error} /> : null}
    {connection.error ? <host.ui.InlineError message={connection.error} /> : null}
    {draft ? <section className="grid gap-3">
      <label className="grid gap-2">服务地址<input aria-label="SenseVoice 服务地址" className={inputClass} value={draft.url} disabled={blocked} onChange={(event) => state.setDraft({ ...draft, url: event.target.value })} /></label>
      <div className="flex gap-4 text-body-sm text-ink-muted"><span>SenseVoiceSmall</span><span>CPU</span></div>
      <div className="flex gap-2">
        <button className={ghostButtonClass} disabled={blocked || !state.dirty} onClick={() => void state.save()}>保存</button>
        <button className={ghostButtonClass} disabled={blocked || state.dirty} onClick={() => void connection.check()}>检查连接</button>
      </div>
      {connection.health ? <p role="status" className="m-0 text-body-sm text-ink-secondary">{connection.health.ready ? "服务就绪" : "服务未就绪"} · {connection.health.model} · {connection.health.device}</p> : null}
    </section> : state.loading ? <span className="text-ink-muted">正在读取设置…</span> : null}
    <TranscriptionTest client={client} host={host} />
  </div>;
}
