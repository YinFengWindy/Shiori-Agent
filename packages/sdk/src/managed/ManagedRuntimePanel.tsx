import { useState } from "react";
import type { PluginSettingsSectionComponentProps } from "../contract/uiModule";
import { errorMessage } from "../errors";
import { ghostButtonClass } from "../styles";
import { useManagedRuntime } from "./useManagedRuntime";

const phaseLabels = { stopped: "已停止", preparing: "正在准备", starting: "正在启动", ready: "服务就绪", cancelled: "已取消", error: "操作失败" };

/** Generic controls for a plugin-owned fixed runtime; the provider supplies its import contract. */
export function ManagedRuntimePanel({ client, host, namespace, importExtensions, disabled = false }: Pick<PluginSettingsSectionComponentProps, "client" | "host"> & {
  namespace: string; importExtensions: string[]; disabled?: boolean;
}) {
  const runtime = useManagedRuntime(client);
  const [importError, setImportError] = useState("");
  const [picking, setPicking] = useState(false);
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
    <div className="text-body-sm text-ink-secondary" role="status">
      {status ? `${phaseLabels[status.phase]} · ${status.revision}` : "正在读取环境状态…"}
    </div>
    {status?.busy && status.total > 0 ? <div className="grid gap-1">
      <progress className="w-full" max={status.total} value={status.received} aria-label="环境准备进度" />
      <span className="text-caption text-ink-muted">{status.item} · {(status.received / 1024 ** 3).toFixed(2)} / {(status.total / 1024 ** 3).toFixed(2)} GiB</span>
    </div> : null}
    {error ? <host.ui.InlineError message={error} /> : null}
    <div className="flex flex-wrap gap-2">
      <button className={ghostButtonClass} disabled={blocked || !status || status.busy} onClick={() => void runtime.run("prepare")}>下载环境</button>
      <button className={ghostButtonClass} disabled={blocked || !status || status.busy} onClick={() => void importPackage()}>导入环境包</button>
      {status?.busy ? <button className={ghostButtonClass} disabled={blocked} onClick={() => void runtime.run("cancel")}>取消准备</button> : null}
      {status?.installed && !status.running ? <button className={ghostButtonClass} disabled={blocked || status.busy} onClick={() => void runtime.run("start")}>启动环境</button> : null}
      {status?.running ? <button className={ghostButtonClass} disabled={blocked || status.busy} onClick={() => void runtime.run("stop")}>停止环境</button> : null}
    </div>
  </section>;
}
