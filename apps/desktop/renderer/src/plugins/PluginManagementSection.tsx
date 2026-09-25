import { useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { settingsGroupStackClass } from "../settings/SettingsFieldPrimitives";
import type { StandaloneSettingsSectionProps } from "../settings/settingsPageTypes";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { InlineError } from "../shared/feedback/InlineError";
import { usePluginManagementController } from "./usePluginManagementController";
import { PluginTrustDialog } from "./PluginTrustDialog";
import { PluginRow } from "./PluginRow";
import { PluginGroupSection } from "./PluginGroupSection";
import { PluginPackageDialogs } from "./PluginPackageDialogs";
import { usePluginPackageController } from "./usePluginPackageController";
import { PluginPackageToolbar } from "./PluginPackageToolbar";
import { PluginRestartBanner } from "./PluginRestartBanner";
import { PluginDetailsDialog } from "./PluginDetailsDialog";
import { pluginDetailsCandidate } from "./pluginPackageState";
import { groupPlugins, pluginProblem } from "./pluginPresentation";
import { pluginUiRegistry } from "./pluginUiRegistry";

/** The parent settings section every plugin's own settings page nests under. */
const PLUGINS_SECTION_ID = "plugins";

/**
 * Settings.section entry: lists every discovered plugin, grouped into
 * 功能 / 渠道 / 系统组件, and lets each be hot enabled/disabled. A plugin
 * with its own settings (a nested 「插件」 subsection) gets a 「设置」
 * action that opens that page through `onSelectSubsection`.
 */
export function PluginManagementSection({ onSelectSubsection }: Partial<StandaloneSettingsSectionProps> = {}) {
  const { plugins, error, pendingIds, setEnabled, reload, runMutation, trustCandidate, requestTrust, confirmTrust, closeTrust } = usePluginManagementController();
  const packages = usePluginPackageController(runMutation);
  const [detailsCandidateId, setDetailsCandidateId] = useState<string | null>(null);
  const detailsPopupRef = useRef<HTMLDivElement>(null);
  const details = pluginDetailsCandidate(plugins, detailsCandidateId);
  const busy = packages.busy || pendingIds.size > 0;

  if (error && !plugins) {
    return (
      <InlineError
        persona="pluginsLoadFailed"
        message={`插件列表加载失败：${error}`}
        actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={() => void reload()}>重新加载</button>}
      />
    );
  }
  if (!plugins) {
    return <div className="text-sm text-ink-muted">正在加载插件列表…</div>;
  }
  // Only an enabled plugin's settings page is reachable (SettingsPage filters nested pages the same way).
  const settingsOpener = (pluginId: string, enabled: boolean) => (
    onSelectSubsection && enabled && pluginUiRegistry.getSettingsSubsection(PLUGINS_SECTION_ID, pluginId)
      ? () => onSelectSubsection(pluginId)
      : undefined
  );
  return (
    <Dialog.Root open={details !== null} onOpenChange={(open) => { if (!open && !busy) setDetailsCandidateId(null); }}>
    <PluginRestartBanner plugins={plugins} />
    <PluginPackageToolbar busy={busy} onInstall={() => void packages.pickPackage()} />
    {error ? <InlineError className="mb-4" message={error} /> : null}
    <div className={settingsGroupStackClass}>
      {groupPlugins(plugins).map((group) => (
        <PluginGroupSection key={group.category} group={group} problemCount={group.plugins.filter((plugin) => pluginProblem(plugin)).length}>
          {group.plugins.map((plugin) => (
            <PluginRow
              key={plugin.candidateId}
              plugin={plugin}
              pending={packages.busy || pendingIds.has(plugin.id)}
              onToggle={(enabled) => void setEnabled(plugin.id, enabled)}
              onTrust={() => requestTrust(plugin)}
              onOpenDetails={() => setDetailsCandidateId(plugin.candidateId)}
              onOpenSettings={settingsOpener(plugin.id, plugin.enabled)}
            />
          ))}
        </PluginGroupSection>
      ))}
    </div>
    <PluginDetailsDialog plugin={details} busy={busy} error={error} popupRef={detailsPopupRef}
      onUpdate={() => { if (details) void packages.pickPackage(details); }}
      onUninstall={() => { if (details) packages.requestUninstall(details); }} />
    <PluginPackageDialogs controller={packages} error={error} detailsPopupRef={detailsPopupRef} />
    <PluginTrustDialog plugin={trustCandidate} busy={Boolean(trustCandidate && pendingIds.has(trustCandidate.id))} error={error} onClose={closeTrust} onConfirm={() => void confirmTrust()} />
    </Dialog.Root>
  );
}
