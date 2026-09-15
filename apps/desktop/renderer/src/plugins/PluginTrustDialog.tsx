import { Dialog } from "@base-ui/react/dialog";
import { ghostButtonClass, primaryButtonClass } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";

/** Explicit trust confirmation for the displayed package identity and content snapshot. */
export function PluginTrustDialog({ plugin, busy, error, onClose, onConfirm }: {
  plugin: PluginSummary | null;
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return <Dialog.Root open={plugin !== null} onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 grid w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-md border border-line bg-surface p-6 shadow-panel">
        <Dialog.Title className="text-title font-semibold text-ink">信任插件</Dialog.Title>
        <div className="grid gap-1 text-body text-ink-secondary">
          <div>{plugin?.name} · {plugin?.version}</div>
          <div className="break-all">{plugin?.trustDirectory || plugin?.directory}</div>
        </div>
        <Dialog.Description className="text-body text-ink-secondary">此插件将与 Shiori 拥有相同权限，可读写文件、访问网络并执行代码。请仅信任来源可靠的插件。</Dialog.Description>
        {error ? <div role="alert" className="text-body text-danger-text">{error}</div> : null}
        <div className="flex justify-end gap-3">
          <button type="button" className={ghostButtonClass} disabled={busy} onClick={onClose}>取消</button>
          <button type="button" className={primaryButtonClass} disabled={busy} onClick={onConfirm}>{busy ? "保存中…" : "确认信任"}</button>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
