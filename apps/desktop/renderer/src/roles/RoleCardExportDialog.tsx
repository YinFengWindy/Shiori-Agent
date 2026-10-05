import { Dialog } from "@base-ui/react/dialog";
import { useState } from "react";
import { DownloadSimple, X } from "@phosphor-icons/react";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, primaryButtonSurfaceClass } from "@yinfengwindy/shiori-sdk";
import type { useRoleCardExport } from "../app/useRoleCardExport";
import { InlineError } from "../shared/feedback/InlineError";
import { compactIconButtonClass, dialogBackdropClass } from "../shared/styles";
import { RoleCardExportPreview } from "./RoleCardExportPreview";
import { RoleCardExportDetails } from "./RoleCardExportDetails";

const secondaryButton = cx(ghostButtonSurfaceClass, compactButtonSizeClass);

/** A focused image-and-definition export dialog with persistent native-save actions. */
export function RoleCardExportDialog({ controller }: { controller: ReturnType<typeof useRoleCardExport> }) {
  const { state, close, selectFormat, save, retry } = controller;
  // Retain the content while Base UI plays the existing reduced-motion-aware exit.
  const [shown, setShown] = useState(state);
  if (state && shown !== state) setShown(state);
  const content = state ?? shown;
  const busy = content?.status === "saving";
  const preview = content?.preview;
  return <Dialog.Root open={Boolean(state)} onOpenChange={(open) => { if (!open) close(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className={dialogBackdropClass} />
      <Dialog.Popup
        finalFocus={() => shown ? document.querySelector<HTMLElement>(`[data-testid="role-card-more-${CSS.escape(shown.roleId)}"]`) : null}
        className="motion-dialog fixed left-1/2 top-1/2 z-50 flex h-[660px] max-h-[calc(100dvh-2rem)] w-[min(820px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-md border border-line bg-surface shadow-panel"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line-soft px-6 py-4">
          <Dialog.Title className="font-display text-title-sm font-semibold text-ink">导出角色</Dialog.Title>
          <button type="button" aria-label="关闭导出" className={compactIconButtonClass} disabled={busy} onClick={close}><X className="h-4 w-4" aria-hidden="true" /></button>
        </header>
        <Dialog.Description className="sr-only">角色卡导出预览</Dialog.Description>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6" aria-busy={content?.status === "loading"}>
          {content ? <div className="grid items-start gap-6 sm:grid-cols-[240px_minmax(0,1fr)] md:grid-cols-[280px_minmax(0,1fr)]">
            <RoleCardExportPreview key={preview?.export_id ?? `${content.roleId}-${content.format}`} preview={preview ?? null} format={content.format} loading={content.status === "loading"} />
            <div className="grid min-w-0 gap-5">
              <RoleCardExportDetails preview={preview ?? null} format={content.format} busy={busy} onSelectFormat={selectFormat} />
              {content.error ? <InlineError message={content.error} actions={<button className={secondaryButton} type="button" onClick={retry}>重新预览</button>} /> : null}
            </div>
          </div> : null}
        </div>
        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-line-soft px-6 py-4">
          <span className="text-caption tabular-nums text-ink-muted">{preview ? `${(preview.size / 1024).toFixed(1)} KB` : ""}</span>
          <div className="flex gap-2">
            <button className={secondaryButton} type="button" disabled={busy} onClick={close}>取消</button>
            <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" disabled={!preview || busy} onClick={() => void save()}>
              <DownloadSimple className="h-4 w-4" aria-hidden="true" />{busy ? "导出中…" : "导出"}
            </button>
          </div>
        </footer>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
