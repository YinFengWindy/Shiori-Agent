import { PlusIcon } from "@phosphor-icons/react";
import { iconButtonClass } from "../shared/styles";

/** Installation is the only package action outside an individual plugin's details. */
export function PluginPackageToolbar({ busy, onInstall }: {
  busy: boolean; onInstall: () => void;
}) {
  return <div role="toolbar" aria-label="插件操作" className="mb-4 flex justify-end gap-2">
    <button type="button" className={iconButtonClass} title="安装插件 ZIP" aria-label="安装插件 ZIP" disabled={busy} onClick={onInstall}>
      <PlusIcon className="h-5 w-5" aria-hidden="true" />
    </button>
  </div>;
}
