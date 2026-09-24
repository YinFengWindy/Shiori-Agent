import { useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { SettingsSectionCard } from "../settings/SettingsFieldPrimitives";
import { cardClass, cx, ghostButtonClass } from "../shared/styles";
import { usePluginManagementController } from "./usePluginManagementController";
import { PluginTrustDialog } from "./PluginTrustDialog";
import { PluginRow } from "./PluginRow";
import { PluginPackageDialogs } from "./PluginPackageDialogs";
import { usePluginPackageController } from "./usePluginPackageController";
import { PluginPackageToolbar } from "./PluginPackageToolbar";
import { PluginRestartBanner } from "./PluginRestartBanner";
import { PluginDetailsDialog } from "./PluginDetailsDialog";
import { pluginDetailsCandidate } from "./pluginPackageState";

/** Settings.section entry: lists every discovered plugin and lets it be hot enabled/disabled. */
export function PluginManagementSection() {
  const { plugins, error, pendingIds, setEnabled, reload, runMutation, trustCandidate, requestTrust, confirmTrust, closeTrust } = usePluginManagementController();
  const packages = usePluginPackageController(runMutation);
  const [detailsCandidateId, setDetailsCandidateId] = useState<string | null>(null);
  const detailsPopupRef = useRef<HTMLDivElement>(null);
  const details = pluginDetailsCandidate(plugins, detailsCandidateId);
  const busy = packages.busy || pendingIds.size > 0;

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
    <Dialog.Root open={details !== null} onOpenChange={(open) => { if (!open && !busy) setDetailsCandidateId(null); }}>
    <PluginRestartBanner plugins={plugins} />
    <PluginPackageToolbar busy={busy} onInstall={() => void packages.pickPackage()} />
    <SettingsSectionCard>
      {error ? <div role="alert" className="text-sm text-danger-text">{error}</div> : null}
      {plugins.map((plugin) => (
        <PluginRow
          key={plugin.candidateId}
          plugin={plugin}
          pending={packages.busy || pendingIds.has(plugin.id)}
          onToggle={(enabled) => void setEnabled(plugin.id, enabled)}
          onTrust={() => requestTrust(plugin)}
          onOpenDetails={() => setDetailsCandidateId(plugin.candidateId)}
        />
      ))}
    </SettingsSectionCard>
    <PluginDetailsDialog plugin={details} busy={busy} error={error} popupRef={detailsPopupRef}
      onUpdate={() => { if (details) void packages.pickPackage(details); }}
      onUninstall={() => { if (details) packages.requestUninstall(details); }} />
    <PluginPackageDialogs controller={packages} error={error} detailsPopupRef={detailsPopupRef} />
    <PluginTrustDialog plugin={trustCandidate} busy={Boolean(trustCandidate && pendingIds.has(trustCandidate.id))} error={error} onClose={closeTrust} onConfirm={() => void confirmTrust()} />
    </Dialog.Root>
  );
}
