import { PlusIcon } from "@phosphor-icons/react";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";

/** Installation is the only package action outside an individual plugin's details. */
export function PluginPackageToolbar({ busy, onInstall }: {
  busy: boolean; onInstall: () => void;
}) {
  return <div role="toolbar" aria-label="插件操作" className="-mt-2 mb-3 flex justify-end gap-2">
    <button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} title="安装插件 ZIP" aria-label="安装插件 ZIP" disabled={busy} onClick={onInstall}>
      <PlusIcon className="h-4 w-4" aria-hidden="true" />
      安装插件
    </button>
  </div>;
}
