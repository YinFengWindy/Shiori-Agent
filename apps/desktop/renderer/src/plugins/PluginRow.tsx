import { Dialog } from "@base-ui/react/dialog";
import { SettingsField } from "../settings/SettingsField";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cx, ghostButtonClass, sidebarNavItemClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";

/** One plugin row: identity, runtime state/diagnostics, and its enable switch. */
export function PluginRow({
  plugin,
  pending,
  onToggle,
  onTrust,
  onOpenDetails,
}: {
  plugin: PluginSummary;
  pending: boolean;
  onToggle: (enabled: boolean) => void;
  onTrust: () => void;
  onOpenDetails: () => void;
}) {
  const hint = [plugin.id, plugin.version && `v${plugin.version}`, plugin.source === "workspace" ? "工作区" : "内置"].filter(Boolean).join(" · ");
  const pendingTrust = plugin.trustPendingRestart && plugin.diagnostic?.code === "trust_required";
  // Backend contributions are already live once setup() succeeds, but the
  // Plugins page must not present the plugin as fully ACTIVE until every
  // declared ui/background entry has confirmed (#262 AC1).
  const activating = plugin.state === "ACTIVE" && plugin.pendingRendererKinds.length > 0;
  const stateLabel = plugin.pendingOperation
    ? `待重启 · ${{ install: "安装", update: "更新", uninstall: "卸载" }[plugin.pendingOperation]}`
    : plugin.trustPendingRestart
    ? "待重启"
    : plugin.state === "UNTRUSTED"
      ? "未信任"
      : plugin.state === "RESTART_REQUIRED"
        ? "需要重启"
        : activating
          ? "激活中…"
          : null;
  return (
    <SettingsField label={
      <Dialog.Trigger className={cx(sidebarNavItemClass, "-my-1 -ml-2 cursor-pointer px-2 py-1 text-left text-body font-medium text-ink hover:text-accent-text")} onClick={onOpenDetails}>
        {plugin.name}
      </Dialog.Trigger>
    } hint={hint || undefined}>
      <div className="grid gap-2">
        <div className="flex items-center justify-end gap-3">
          {stateLabel ? <span className="text-caption text-ink-muted">{stateLabel}</span> : null}
          {plugin.canTrust ? <button type="button" className={ghostButtonClass} disabled={pending} onClick={onTrust}>信任…</button> : null}
          {plugin.canToggle && plugin.supportsHotUnload === false ? <span className="text-caption text-ink-muted">更改需重启</span> : null}
          <SettingsToggleCard
            checked={plugin.enabled && (plugin.canToggle || Boolean(plugin.pendingOperation))}
            disabled={pending || !plugin.canToggle}
            ariaLabel={`启用 ${plugin.name}`}
            onChange={onToggle}
          />
        </div>
        {plugin.error && !pendingTrust ? <span className="line-clamp-2 break-words text-body text-danger-text">{plugin.error}</span> : null}
        {plugin.trustPendingRestart ? <span className="text-body text-ink-secondary">信任已保存，重启 Shiori 后加载。</span> : null}
        {plugin.pendingOperation === "update" ? <span className="text-body text-ink-secondary">{plugin.version} → {plugin.pendingVersion}</span> : null}
        {plugin.packageOperationError ? <span role="alert" className="break-words text-body text-danger-text">操作失败 · {plugin.packageOperationError}</span> : null}
        {plugin.rendererError ? <span className="break-words text-body text-danger-text">UI FAILED · {plugin.rendererError}</span> : null}
      </div>
    </SettingsField>
  );
}

