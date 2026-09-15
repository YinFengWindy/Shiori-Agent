import { SettingsField } from "../settings/SettingsField";
import { SettingsSectionCard } from "../settings/SettingsFieldPrimitives";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cardClass, cx, ghostButtonClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";
import { usePluginManagementController } from "./usePluginManagementController";

/** One plugin row: identity, runtime state/diagnostics, and its enable switch. */
function PluginRow({
  plugin,
  pending,
  onToggle,
}: {
  plugin: PluginSummary;
  pending: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const hint = [plugin.id, plugin.version && `v${plugin.version}`, plugin.source === "workspace" ? "工作区" : "内置", plugin.description].filter(Boolean).join(" · ");
  return (
    <SettingsField label={plugin.name} hint={hint || undefined}>
      <div className="grid gap-2">
        <div className="flex items-center justify-end gap-3">
          <span className="text-caption text-ink-muted">{plugin.state}</span>
          {plugin.canToggle && plugin.supportsHotUnload === false ? <span className="text-caption text-ink-muted">更改需重启</span> : null}
          <SettingsToggleCard
            checked={plugin.canToggle && plugin.enabled}
            disabled={pending || !plugin.canToggle}
            ariaLabel={`启用 ${plugin.name}`}
            onChange={onToggle}
          />
        </div>
        {plugin.error ? <span className="line-clamp-2 break-words text-body text-danger-text">{plugin.error}</span> : null}
        <details className="text-caption text-ink-muted">
          <summary className="cursor-pointer">详情</summary>
          <div className="mt-2 grid gap-1 break-all">
            <span>{plugin.directory}</span>
            {plugin.diagnostic ? <>
              <span>{plugin.diagnostic.code} · {plugin.diagnostic.stage} · {plugin.diagnostic.field}</span>
              <span>{plugin.diagnostic.reason}</span>
              {plugin.diagnostic.path ? <span>{plugin.diagnostic.path}</span> : null}
            </> : null}
          </div>
        </details>
      </div>
    </SettingsField>
  );
}

/** Settings.section entry: lists every discovered plugin and lets it be hot enabled/disabled. */
export function PluginManagementSection() {
  const { plugins, error, pendingIds, setEnabled, reload } = usePluginManagementController();

  if (error && !plugins) {
    return (
      <div className={cx(cardClass, "p-6 text-sm leading-6 text-danger-text")}>
        插件列表加载失败：{error}
        <button type="button" className={cx(ghostButtonClass, "ml-3")} onClick={() => void reload()}>重新加载</button>
      </div>
    );
  }
  if (!plugins) {
    return <div className="text-sm text-ink-muted">正在加载插件列表…</div>;
  }
  return (
    <SettingsSectionCard>
      {error ? <div role="alert" className="text-sm text-danger-text">{error}</div> : null}
      {plugins.map((plugin) => (
        <PluginRow
          key={plugin.candidateId}
          plugin={plugin}
          pending={pendingIds.has(plugin.id)}
          onToggle={(enabled) => void setEnabled(plugin.id, enabled)}
        />
      ))}
    </SettingsSectionCard>
  );
}
