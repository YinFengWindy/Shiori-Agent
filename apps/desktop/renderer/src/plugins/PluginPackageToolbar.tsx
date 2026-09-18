import { ArrowClockwiseIcon, PlusIcon, TrashIcon } from "@phosphor-icons/react";
import { iconButtonClass } from "../shared/styles";

/** One compact toolbar; update and removal require an explicit external-package selection. */
export function PluginPackageToolbar({ busy, hasSelection, onInstall, onUpdate, onUninstall }: {
  busy: boolean; hasSelection: boolean; onInstall: () => void; onUpdate: () => void; onUninstall: () => void;
}) {
  return <div role="toolbar" aria-label="插件操作" className="mb-4 flex justify-end gap-2">
    <button type="button" className={iconButtonClass} title="安装插件 ZIP" aria-label="安装插件 ZIP" disabled={busy} onClick={onInstall}>
      <PlusIcon className="h-5 w-5" aria-hidden="true" />
    </button>
    <button type="button" className={iconButtonClass} title="更新插件" aria-label="更新插件" disabled={busy || !hasSelection} onClick={onUpdate}>
      <ArrowClockwiseIcon className="h-5 w-5" aria-hidden="true" />
    </button>
    <button type="button" className={iconButtonClass} title="卸载插件" aria-label="卸载插件" disabled={busy || !hasSelection} onClick={onUninstall}>
      <TrashIcon className="h-5 w-5" aria-hidden="true" />
    </button>
  </div>;
}
