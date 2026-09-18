import { useState } from "react";
import { SettingsSectionCard } from "../settings/SettingsFieldPrimitives";
import { cardClass, cx, ghostButtonClass } from "../shared/styles";
import { usePluginManagementController } from "./usePluginManagementController";
import { PluginTrustDialog } from "./PluginTrustDialog";
import { PluginRow } from "./PluginRow";
import { PluginPackageDialogs } from "./PluginPackageDialogs";
import { usePluginPackageController } from "./usePluginPackageController";
import { PluginPackageToolbar } from "./PluginPackageToolbar";
import { canManagePluginPackage, selectedPluginPackage } from "./pluginPackageSelection";

/** Settings.section entry: lists every discovered plugin and lets it be hot enabled/disabled. */
export function PluginManagementSection() {
  const { plugins, error, pendingIds, setEnabled, reload, runMutation, trustCandidate, requestTrust, confirmTrust, closeTrust } = usePluginManagementController();
  const packages = usePluginPackageController(runMutation);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const selected = selectedPluginPackage(plugins, selectedCandidateId);

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
    <><PluginPackageToolbar busy={packages.busy || pendingIds.size > 0} hasSelection={selected !== null}
      onInstall={() => void packages.pickPackage()} onUpdate={() => { if (selected) void packages.pickPackage(selected); }}
      onUninstall={() => { if (selected) packages.requestUninstall(selected); }} />
    <SettingsSectionCard>
      {error ? <div role="alert" className="text-sm text-danger-text">{error}</div> : null}
      {plugins.map((plugin) => (
        <PluginRow
          key={plugin.candidateId}
          plugin={plugin}
          pending={packages.busy || pendingIds.has(plugin.id)}
          onToggle={(enabled) => void setEnabled(plugin.id, enabled)}
          onTrust={() => requestTrust(plugin)}
          selectable={canManagePluginPackage(plugin)}
          selected={selected?.candidateId === plugin.candidateId}
          onSelect={() => setSelectedCandidateId(plugin.candidateId)}
        />
      ))}
    </SettingsSectionCard>
    <PluginPackageDialogs controller={packages} error={error} />
    <PluginTrustDialog plugin={trustCandidate} busy={Boolean(trustCandidate && pendingIds.has(trustCandidate.id))} error={error} onClose={closeTrust} onConfirm={() => void confirmTrust()} /></>
  );
}
