import { useState } from "react";
import type { PluginSettingsSectionComponentProps } from "../contract/uiModule";
import { errorMessage } from "../errors";
import { compactGhostButtonClass } from "../styles";
import { useManagedRuntime, type ManagedRuntimeStatus } from "./useManagedRuntime";

const phaseLabels = { stopped: "已停止", preparing: "正在准备", starting: "正在启动", removing: "正在删除", ready: "服务就绪", cancelled: "已取消", error: "操作失败" };

function gib(bytes: number, digits = 1) {
  return `${(bytes / 1024 ** 3).toFixed(digits)} GiB`;
}

/** What a removal deletes, with the kept cache size when there is one; else the leftover temp/cache files. */
function removalDescription(status: ManagedRuntimeStatus | null) {
  const parts = [
    ...(status?.installed ? ["已安装的环境"] : []),
    ...(status && status.reclaimable > 0 ? [`下载缓存（${gib(status.reclaimable, 2)}）`] : []),
    ...(status?.staging ? ["未完成的准备文件"] : []),
  ];
  return `${(parts.length ? parts : ["未完成的准备文件与缓存"]).join("与")}将被删除。`;
}

/**
 * The figures the backend's free-space check uses: a download and the provider's import,
 * then the volume's free space. An installed environment shows only the free space.
 */
function spaceSummary(status: ManagedRuntimeStatus) {
  const free = `剩余 ${status.free === null ? "未知" : gib(status.free)}`;
  if (status.installed) return { text: free, insufficient: false };
  const insufficient = status.free !== null && status.free < Math.min(status.required, status.required_import);
  return { text: `下载需约 ${gib(status.required)} · 导入需约 ${gib(status.required_import)} · ${free}`, insufficient };
}

/**
 * Generic controls for a plugin-owned fixed runtime; the provider supplies its import extensions.
 * Imports are picked by original path (`host.pickFilePaths`) and never copied; the install
 * location is picked with `host.pickDirectory` and can change only while nothing is installed.
 */
export function ManagedRuntimePanel({ client, host, importExtensions, disabled = false }: Pick<PluginSettingsSectionComponentProps, "client" | "host"> & {
  importExtensions: string[]; disabled?: boolean;
}) {
  const runtime = useManagedRuntime(client);
  const [importError, setImportError] = useState("");
  const [picking, setPicking] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const { status } = runtime;
  const blocked = disabled || picking || runtime.pending;
  async function importPackage() {
    setPicking(true); setImportError("");
    try {
      const [source] = await host.pickFilePaths({ multiple: false, maxFileBytes: 16 * 1024 ** 3,
        filters: [{ name: "环境资源包", extensions: importExtensions }] });
      if (source) await runtime.run("prepare", source);
    } catch (cause) { setImportError(errorMessage(cause)); }
    finally { setPicking(false); }
  }
  async function changeLocation() {
    setPicking(true); setImportError("");
    try {
      const directory = await host.pickDirectory();
      if (directory) await runtime.relocate(directory);
    } catch (cause) { setImportError(errorMessage(cause)); }
    finally { setPicking(false); }
  }
  const space = status ? spaceSummary(status) : null;
  const error = importError || runtime.error || status?.error;
  return <section className="grid gap-3" aria-label="托管推理环境">
    {/* Status and actions share one row: status left, buttons right. */}
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="min-w-0 text-body-sm text-ink-secondary" role="status">
        {status ? `${phaseLabels[status.phase]} · ${status.revision}` : "正在读取环境状态…"}
      </div>
      <div className="ml-auto flex flex-wrap justify-end gap-2">
        <button type="button" className={compactGhostButtonClass} disabled={blocked || !status || status.busy} onClick={() => void runtime.run("prepare")}>下载环境</button>
        <button type="button" className={compactGhostButtonClass} disabled={blocked || !status || status.busy} onClick={() => void importPackage()}>导入环境包</button>
        {status?.busy && status.phase !== "removing" ? <button type="button" className={compactGhostButtonClass} disabled={blocked} onClick={() => void runtime.run("cancel")}>取消准备</button> : null}
        {status?.installed && !status.running ? <button type="button" className={compactGhostButtonClass} disabled={blocked || status.busy} onClick={() => void runtime.run("start")}>启动环境</button> : null}
        {status?.running ? <button type="button" className={compactGhostButtonClass} disabled={blocked || status.busy} onClick={() => void runtime.run("stop")}>停止环境</button> : null}
        {/* Removal needs a stopped service and no running task; the backend enforces the same rule. */}
        {status?.removable ? <button type="button" className={compactGhostButtonClass} disabled={blocked || status.busy || status.running} onClick={() => setConfirmRemove(true)}>删除环境</button> : null}
      </div>
    </div>
    {/* Location and space; both location actions need nothing installed or kept. */}
    {status && space ? <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="grid min-w-0 gap-0.5 text-caption">
        <span className="break-all text-ink-secondary" title={status.location}>安装位置：{status.location || "未知"}</span>
        <span className={space.insufficient ? "text-danger-text" : "text-ink-muted"}>{space.text}</span>
      </div>
      <div className="ml-auto flex flex-wrap justify-end gap-2">
        <button type="button" className={compactGhostButtonClass} disabled={blocked || !status.relocatable} onClick={() => void changeLocation()}>更改位置</button>
        {status.customized ? <button type="button" className={compactGhostButtonClass} disabled={blocked || !status.relocatable} onClick={() => void runtime.relocate()}>恢复默认</button> : null}
      </div>
    </div> : null}
    {status?.busy && status.total > 0 ? <div className="grid gap-1">
      <progress className="w-full" max={status.total} value={status.received} aria-label="环境准备进度" />
      <span className="text-caption text-ink-muted">{status.item} · {(status.received / 1024 ** 3).toFixed(2)} / {gib(status.total, 2)}</span>
    </div> : null}
    {error ? <host.ui.InlineError message={error} /> : null}
    <host.ui.ConfirmDialog open={confirmRemove} destructive persona="destructive" title="删除托管环境" description={removalDescription(status)} confirmLabel="删除环境"
      onClose={() => setConfirmRemove(false)} onConfirm={() => { setConfirmRemove(false); void runtime.run("remove"); }} />
  </section>;
}
