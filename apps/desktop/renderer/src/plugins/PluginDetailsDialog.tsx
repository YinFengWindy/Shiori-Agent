import { Dialog } from "@base-ui/react/dialog";
import { useState, type RefObject } from "react";
import { CaretRight, WarningCircle, XIcon } from "@phosphor-icons/react";
import { dangerGhostButtonClass, ghostButtonClass, iconButtonClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";
import { canManagePluginPackage } from "./pluginPackageState";
import { pluginDisplayName, pluginProblem } from "./pluginPresentation";

/**
 * Read-only candidate details with guarded package actions inside the
 * management dialog root. The description and a readable problem line come
 * first; ids, paths, diagnostic codes and raw error text sit in the
 * 「开发者详情」 disclosure.
 */
export function PluginDetailsDialog({ plugin: currentPlugin, busy, error, popupRef, onUpdate, onUninstall }: {
  plugin: PluginSummary | null;
  busy: boolean;
  error: string;
  popupRef?: RefObject<HTMLDivElement | null>;
  onUpdate: () => void;
  onUninstall: () => void;
}) {
  // The owner clears the candidate as it closes; keep the last one rendered
  // so the exit animation does not play on an emptied dialog.
  const [lastPlugin, setLastPlugin] = useState(currentPlugin);
  if (currentPlugin && currentPlugin !== lastPlugin) setLastPlugin(currentPlugin);
  const plugin = currentPlugin ?? lastPlugin;
  const pendingTrust = plugin?.trustPendingRestart && plugin.diagnostic?.code === "trust_required";
  const problem = plugin ? pluginProblem(plugin) : null;
  return <Dialog.Portal>
    <Dialog.Backdrop className="confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
    <Dialog.Popup ref={popupRef} className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-md border border-line bg-surface p-6 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <Dialog.Title className="min-w-0 break-words font-display text-title font-semibold text-ink">{plugin ? pluginDisplayName(plugin) : null}</Dialog.Title>
        <Dialog.Close className={iconButtonClass} aria-label="关闭插件详情" disabled={busy}>
          <XIcon className="h-5 w-5" aria-hidden="true" />
        </Dialog.Close>
      </div>
      {plugin ? <>
        <div className="scrollbar-soft grid min-h-0 content-start gap-4 overflow-y-auto overscroll-contain">
          {plugin.description ? <p className="m-0 whitespace-pre-wrap break-words text-body text-ink-secondary">{plugin.description}</p> : null}
          {problem ? (
            <p className="m-0 flex items-center gap-1.5 text-body text-danger-text">
              <WarningCircle className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
              {problem}
            </p>
          ) : null}
          {plugin.pendingOperation === "update" ? <p className="m-0 text-body text-ink-secondary">{plugin.version} → {plugin.pendingVersion}</p> : null}
          {plugin.pendingOperation || plugin.trustPendingRestart ? <p className="m-0 text-body text-ink-secondary">待重启 · 重启 Shiori 后生效。</p> : null}
          {error ? <p role="alert" className="m-0 break-words text-body text-danger-text">{error}</p> : null}
          <details className="group rounded-md border border-line-soft bg-surface-soft">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-body-sm font-medium text-ink-secondary [&::-webkit-details-marker]:hidden">
              <CaretRight className="h-3.5 w-3.5 text-ink-muted transition-transform duration-quick ease-out-soft group-open:rotate-90" weight="bold" aria-hidden="true" />
              开发者详情
            </summary>
            <dl className="m-0 grid gap-3 break-words border-t border-line-soft px-3 py-3 text-body-sm">
              <div><dt className="text-ink-muted">ID</dt><dd className="m-0 break-all font-mono text-ink">{plugin.id}</dd></div>
              <div><dt className="text-ink-muted">版本</dt><dd className="m-0 text-ink">{plugin.version || "—"}{plugin.pendingOperation === "update" ? ` → ${plugin.pendingVersion}` : ""}</dd></div>
              <div><dt className="text-ink-muted">来源</dt><dd className="m-0 text-ink">{plugin.source === "workspace" ? "工作区" : "内置"}</dd></div>
              <div><dt className="text-ink-muted">实际路径</dt><dd className="m-0 break-all text-ink-secondary">{plugin.directory}</dd></div>
              {plugin.diagnostic && !pendingTrust ? <div>
                <dt className="text-ink-muted">诊断</dt>
                <dd className="m-0 grid gap-1 text-danger-text">
                  <span className="font-mono">{plugin.diagnostic.code} · {plugin.diagnostic.stage} · {plugin.diagnostic.field}</span>
                  <span className="whitespace-pre-wrap">{plugin.diagnostic.reason}</span>
                  {plugin.diagnostic.path ? <span className="break-all">{plugin.diagnostic.path}</span> : null}
                </dd>
              </div> : null}
              {plugin.error && !pendingTrust ? <div><dt className="text-ink-muted">错误</dt><dd className="m-0 whitespace-pre-wrap break-words text-danger-text">{plugin.error}</dd></div> : null}
              {plugin.packageOperationError ? <div><dt className="text-ink-muted">安装记录</dt><dd role="alert" className="m-0 break-words text-danger-text">操作失败 · {plugin.packageOperationError}</dd></div> : null}
              {plugin.rendererError ? <div><dt className="text-ink-muted">界面</dt><dd className="m-0 break-words text-danger-text">界面加载失败 · {plugin.rendererError}</dd></div> : null}
            </dl>
          </details>
        </div>
        {canManagePluginPackage(plugin) ? <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-line-soft pt-4">
          <button type="button" data-plugin-action="update" className={ghostButtonClass} disabled={busy} onClick={onUpdate}>从 ZIP 更新</button>
          <button type="button" data-plugin-action="uninstall" className={dangerGhostButtonClass} disabled={busy} onClick={onUninstall}>卸载插件</button>
        </div> : null}
      </> : null}
    </Dialog.Popup>
  </Dialog.Portal>;
}
