import { Dialog } from "@base-ui/react/dialog";
import type { RefObject } from "react";
import { XIcon } from "@phosphor-icons/react";
import { dangerGhostButtonClass, ghostButtonClass, iconButtonClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";
import { canManagePluginPackage } from "./pluginPackageState";

/** Read-only candidate details with guarded package actions inside the management dialog root. */
export function PluginDetailsDialog({ plugin, busy, error, popupRef, onUpdate, onUninstall }: {
  plugin: PluginSummary | null;
  busy: boolean;
  error: string;
  popupRef?: RefObject<HTMLDivElement | null>;
  onUpdate: () => void;
  onUninstall: () => void;
}) {
  const pendingTrust = plugin?.trustPendingRestart && plugin.diagnostic?.code === "trust_required";
  return <Dialog.Portal>
    <Dialog.Backdrop className="confirm-dialog-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
    <Dialog.Popup ref={popupRef} className="confirm-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-md border border-line bg-surface p-6 shadow-panel">
      <div className="flex items-start justify-between gap-4">
        <Dialog.Title className="min-w-0 break-words font-display text-title font-semibold text-ink">{plugin?.name}</Dialog.Title>
        <Dialog.Close className={iconButtonClass} aria-label="关闭插件详情" disabled={busy}>
          <XIcon className="h-5 w-5" aria-hidden="true" />
        </Dialog.Close>
      </div>
      {plugin ? <>
        <div className="scrollbar-soft min-h-0 overflow-y-auto overscroll-contain">
          <dl className="grid gap-4 break-words text-body">
            <div><dt className="text-ink-muted">ID</dt><dd className="break-all text-ink">{plugin.id}</dd></div>
            <div><dt className="text-ink-muted">版本</dt><dd className="text-ink">{plugin.version || "—"}{plugin.pendingOperation === "update" ? ` → ${plugin.pendingVersion}` : ""}</dd></div>
            <div><dt className="text-ink-muted">来源</dt><dd className="text-ink">{plugin.source === "workspace" ? "工作区" : "内置"}</dd></div>
            <div><dt className="text-ink-muted">描述</dt><dd className="whitespace-pre-wrap text-ink-secondary">{plugin.description || "—"}</dd></div>
            <div><dt className="text-ink-muted">实际路径</dt><dd className="break-all text-ink-secondary">{plugin.directory}</dd></div>
            {plugin.diagnostic && !pendingTrust ? <div>
              <dt className="text-ink-muted">诊断</dt>
              <dd className="grid gap-1 text-danger-text">
                <span>{plugin.diagnostic.code} · {plugin.diagnostic.stage} · {plugin.diagnostic.field}</span>
                <span className="whitespace-pre-wrap">{plugin.diagnostic.reason}</span>
                {plugin.diagnostic.path ? <span className="break-all">{plugin.diagnostic.path}</span> : null}
              </dd>
            </div> : null}
          </dl>
          {plugin.error && !pendingTrust ? <p className="mt-4 whitespace-pre-wrap break-words text-body text-danger-text">{plugin.error}</p> : null}
          {plugin.packageOperationError ? <p role="alert" className="mt-4 break-words text-body text-danger-text">操作失败 · {plugin.packageOperationError}</p> : null}
          {plugin.rendererError ? <p className="mt-4 break-words text-body text-danger-text">UI FAILED · {plugin.rendererError}</p> : null}
          {plugin.pendingOperation || plugin.trustPendingRestart ? <p className="mt-4 text-body text-ink-secondary">待重启 · 重启 Shiori 后生效。</p> : null}
          {error ? <p role="alert" className="mt-4 break-words text-body text-danger-text">{error}</p> : null}
        </div>
        {canManagePluginPackage(plugin) ? <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-line-soft pt-4">
          <button type="button" data-plugin-action="update" className={ghostButtonClass} disabled={busy} onClick={onUpdate}>从 ZIP 更新</button>
          <button type="button" data-plugin-action="uninstall" className={dangerGhostButtonClass} disabled={busy} onClick={onUninstall}>卸载插件</button>
        </div> : null}
      </> : null}
    </Dialog.Popup>
  </Dialog.Portal>;
}
