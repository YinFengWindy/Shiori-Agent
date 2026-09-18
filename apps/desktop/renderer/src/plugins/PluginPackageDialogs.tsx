import type { RefObject } from "react";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { pluginTrustDisclosure } from "./pluginTrustDisclosure";
import type { usePluginPackageController } from "./usePluginPackageController";

/** Installation requires full trust; removal keeps independent data unless explicitly selected. */
export function PluginPackageDialogs({ controller, error, detailsPopupRef }: {
  controller: ReturnType<typeof usePluginPackageController>;
  error: string;
  detailsPopupRef: RefObject<HTMLDivElement | null>;
}) {
  const { preview, uninstallCandidate, deleteData, setDeleteData, busy } = controller;
  const updating = preview?.action === "update";
  const restoreDetailsFocus = (action: "update" | "uninstall") => {
    const popup = detailsPopupRef.current;
    if (!popup) return true;
    const trigger = popup.querySelector<HTMLButtonElement>(`[data-plugin-action="${action}"]`);
    // Successful mutations can remove their action while details remain open.
    return trigger && !trigger.disabled ? trigger : popup;
  };
  return <>
    <ConfirmDialog busyLabel="处理中…" destructive={false} open={preview !== null} title={updating ? "更新插件" : "安装插件"}
      description={pluginTrustDisclosure} confirmLabel={updating ? "信任并更新" : "信任并安装"}
      busy={busy} error={error} finalFocus={() => restoreDetailsFocus("update")} onClose={() => void controller.cancel()} onConfirm={() => void controller.confirm()}>
      <div className="grid gap-1 break-all text-body text-ink-secondary">
        <span>{preview?.name}{preview && preview.name !== preview.id ? ` · ${preview.id}` : ""}</span>
        <span>{updating ? `${preview?.previous_version} → ` : ""}{preview?.version}</span>
        <span>{preview?.source_name}</span>
        <span>{preview?.directory}</span>
        <span>重启 Shiori 后生效。</span>
      </div>
    </ConfirmDialog>
    <ConfirmDialog busyLabel="处理中…" destructive open={uninstallCandidate !== null} title="卸载插件" confirmLabel="卸载"
      description="重启 Shiori 后完成卸载。默认保留插件数据和配置。"
      busy={busy} error={error} finalFocus={() => restoreDetailsFocus("uninstall")} onClose={controller.closeUninstall} onConfirm={() => void controller.uninstall()}>
      <div className="grid gap-2 text-body text-ink-secondary">
        <span>{uninstallCandidate?.name} · {uninstallCandidate?.version}</span>
        <label className="flex items-center gap-2">
          <input type="checkbox" className="h-4 w-4 accent-accent" checked={deleteData} disabled={busy} onChange={(event) => setDeleteData(event.target.checked)} />
          同时删除插件数据
        </label>
        {deleteData ? <span className="text-danger-text">插件的独立数据和配置将在重启时永久删除。</span> : null}
      </div>
    </ConfirmDialog>
  </>;
}
