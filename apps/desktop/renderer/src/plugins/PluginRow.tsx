import { Dialog } from "@base-ui/react/dialog";
import { GearSix, WarningCircle } from "@phosphor-icons/react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, sidebarNavItemClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";
import { pluginDisplayName, pluginProblem, pluginStateLabel } from "./pluginPresentation";

/** Pending/transitional state tag; lavender keeps it apart from the accent-colored actions. */
const stateBadgeClass = "inline-flex items-center rounded-full bg-lavender-soft px-2.5 py-0.5 text-caption text-lavender-text";

/**
 * One plugin row: display name (opens the details dialog), one-line
 * description, state and a readable problem line, then the actions — trust,
 * the plugin's own settings page when it has one, and the enable switch.
 */
export function PluginRow({
  plugin,
  pending,
  onToggle,
  onTrust,
  onOpenDetails,
  onOpenSettings,
}: {
  plugin: PluginSummary;
  pending: boolean;
  onToggle: (enabled: boolean) => void;
  onTrust: () => void;
  onOpenDetails: () => void;
  /** Present when the plugin has a settings page (a registered 「插件」 nested subsection). */
  onOpenSettings?: () => void;
}) {
  const name = pluginDisplayName(plugin);
  const stateLabel = pluginStateLabel(plugin);
  const problem = pluginProblem(plugin);
  return (
    <div className="flex items-start gap-3 border-b border-line-soft py-4 last:border-b-0" data-plugin-row={plugin.id}>
      <div className="grid min-w-0 flex-1 gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <Dialog.Trigger className={cx(sidebarNavItemClass, "-my-0.5 -ml-1.5 min-w-0 cursor-pointer truncate px-1.5 py-0.5 text-left text-body font-medium text-ink hover:text-accent-text")} onClick={onOpenDetails}>
            {name}
          </Dialog.Trigger>
          {stateLabel ? <span className={stateBadgeClass}>{stateLabel}</span> : null}
        </div>
        {plugin.description ? <p className="m-0 truncate text-caption text-ink-muted" title={plugin.description}>{plugin.description}</p> : null}
        {problem ? (
          <p className="m-0 flex items-center gap-1 text-caption text-danger-text">
            <WarningCircle className="h-3.5 w-3.5 shrink-0" weight="bold" aria-hidden="true" />
            {problem}
          </p>
        ) : null}
        {plugin.trustPendingRestart ? <p className="m-0 text-caption text-ink-secondary">信任已保存，重启 Shiori 后加载。</p> : null}
        {plugin.pendingOperation === "update" ? <p className="m-0 text-caption text-ink-secondary">{plugin.version} → {plugin.pendingVersion}</p> : null}
        {plugin.canToggle && plugin.supportsHotUnload === false ? <p className="m-0 text-caption text-ink-muted">更改需重启</p> : null}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {plugin.canTrust ? <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} disabled={pending} onClick={onTrust}>信任…</button> : null}
        {onOpenSettings ? (
          <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} aria-label={`${name} 设置`} onClick={onOpenSettings}>
            <GearSix className="h-4 w-4" aria-hidden="true" />
            设置
          </button>
        ) : null}
        <SettingsToggleCard
          checked={plugin.enabled && (plugin.canToggle || Boolean(plugin.pendingOperation))}
          disabled={pending || !plugin.canToggle}
          ariaLabel={`启用 ${name}`}
          onChange={onToggle}
        />
      </div>
    </div>
  );
}
