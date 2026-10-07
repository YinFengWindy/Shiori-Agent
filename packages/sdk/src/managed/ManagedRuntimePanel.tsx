import { useState } from "react";
import type { PluginSettingsSectionComponentProps } from "../contract/uiModule";
import { errorMessage } from "../errors";
import { compactGhostButtonClass } from "../styles";
import { useManagedRuntime, type ManagedRuntimeStatus } from "./useManagedRuntime";

const phaseLabels = { stopped: "已停止", preparing: "正在准备", starting: "正在启动", removing: "正在删除", ready: "服务就绪", cancelled: "已取消", error: "操作失败" };

/** What a removal deletes, with the kept cache size when there is one. */
function removalDescription(status: ManagedRuntimeStatus | null) {
  const parts = [
    ...(status?.installed ? ["已安装的环境"] : []),
    status && status.reclaimable > 0 ? `下载缓存（${(status.reclaimable / 1024 ** 3).toFixed(2)} GiB）` : "下载缓存",
    ...(status?.staging ? ["未完成的准备文件"] : []),
  ];
  return `${parts.join("与")}将被删除。`;
}

/** Generic controls for a plugin-owned fixed runtime; the provider supplies its import contract. */
export function ManagedRuntimePanel({ client, host, namespace, importExtensions, disabled = false }: Pick<PluginSettingsSectionComponentProps, "client" | "host"> & {
  namespace: string; importExtensions: string[]; disabled?: boolean;
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
      const [source] = await host.pickFiles({ namespace, multiple: false, maxFileBytes: 16 * 1024 ** 3,
        filters: [{ name: "环境资源包", extensions: importExtensions }] });
      if (source) await runtime.run("prepare", source);
    } catch (cause) { setImportError(errorMessage(cause)); }
    finally { setPicking(false); }
  }
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
        {status && (status.installed || status.reclaimable > 0 || status.staging) ? <button type="button" className={compactGhostButtonClass} disabled={blocked || status.busy || status.running} onClick={() => setConfirmRemove(true)}>删除环境</button> : null}
      </div>
    </div>
    {status?.busy && status.total > 0 ? <div className="grid gap-1">
      <progress className="w-full" max={status.total} value={status.received} aria-label="环境准备进度" />
      <span className="text-caption text-ink-muted">{status.item} · {(status.received / 1024 ** 3).toFixed(2)} / {(status.total / 1024 ** 3).toFixed(2)} GiB</span>
    </div> : null}
    {error ? <host.ui.InlineError message={error} /> : null}
    <host.ui.ConfirmDialog open={confirmRemove} destructive persona="destructive" title="删除托管环境" description={removalDescription(status)} confirmLabel="删除环境"
      onClose={() => setConfirmRemove(false)} onConfirm={() => { setConfirmRemove(false); void runtime.run("remove"); }} />
  </section>;
}
