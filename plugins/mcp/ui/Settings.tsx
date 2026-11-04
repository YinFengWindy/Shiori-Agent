import { useRef, useState } from "react";
import { compactGhostButtonClass, settingsGroupStackClass, SettingsGroup, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import { rpcMethods } from "../rpcMethods.generated";
import { ServerEditor } from "./ServerEditor";
import { useMcpServers } from "./useMcpServers";
import type { McpServer } from "./types";

const statuses: Record<string, string> = { disabled: "已停用", disconnected: "未连接", connecting: "连接中", connected: "已连接", error: "连接失败", disabling: "停止中" };
const operations: Record<string, string> = { connect: "连接", test: "测试连接", disable: "停用", delete: "删除", cancel: "取消" };
const outcomes: Record<string, string> = { running: "进行中", succeeded: "成功", failed: "失败", cancelled: "已取消" };

/** Workspace-wide MCP management in Settings > Plugins > MCP. */
export function McpSettings({ client, host }: PluginSettingsSectionComponentProps) {
  const state = useMcpServers(client);
  const [editing, setEditing] = useState<McpServer | "new" | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const add = useRef<HTMLButtonElement>(null);
  const close = () => { setEditing(null); requestAnimationFrame(() => add.current?.focus()); };
  const snapshot = state.snapshot;
  return <div className={settingsGroupStackClass}>
    {(state.error || snapshot?.error) ? <host.ui.InlineError message={state.error || snapshot?.error || ""} actions={<button type="button" className={compactGhostButtonClass} onClick={() => { void state.reload(); }}>重新载入</button>} /> : null}
    <div role="status" className="text-body-sm text-ink-muted">{!snapshot || snapshot.loading ? "正在读取服务器…" : ""}</div>
    <div><button ref={add} type="button" className={compactGhostButtonClass} disabled={state.busy || !!snapshot?.error || !snapshot || snapshot.loading} onClick={() => setEditing("new")}>添加服务器</button></div>
    {editing ? <ServerEditor key={editing === "new" ? "new" : editing.id} server={editing === "new" ? null : editing} busy={state.busy} save={(payload) => state.run(rpcMethods["servers.save"], payload)} cancel={close} /> : null}
    {snapshot?.servers.map((server) => <SettingsGroup key={server.id} title={server.label}>
      <div className="grid gap-3 py-4">
        <div className="flex flex-wrap items-center gap-3 text-body-sm"><span className="break-all text-ink-muted">{server.id}</span><span>{server.transport.kind === "stdio" ? "stdio" : "Streamable HTTP"}</span><span role="status">{statuses[server.status] ?? server.status}</span><span>{server.selection.mode === "all" ? "全部工具" : `已选择 ${server.selection.names.length} 个工具`}</span></div>
        {server.error ? <host.ui.InlineError message={server.error} /> : null}
        {server.operation ? <div role="status" className="text-body-sm text-ink-muted">{operations[server.operation.kind]}：{outcomes[server.operation.status]}{server.operation.error ? ` · ${server.operation.error}` : ""}</div> : null}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={compactGhostButtonClass} disabled={state.busy} onClick={() => setEditing(server)}>编辑 {server.label}</button>
          <button type="button" className={compactGhostButtonClass} disabled={state.busy} onClick={() => { void state.run(rpcMethods["servers.set_enabled"], { server_id: server.id, expected_revision: server.revision, enabled: !server.enabled }); }}>{server.enabled ? "停用" : "启用"}</button>
          <button type="button" className={compactGhostButtonClass} disabled={state.busy || server.operation?.status === "running"} onClick={() => { void state.run(rpcMethods["servers.test"], { server_id: server.id }); }}>测试连接</button>
          <button type="button" className={compactGhostButtonClass} disabled={state.busy || !server.enabled} onClick={() => { void state.run(rpcMethods["servers.reconnect"], { server_id: server.id }); }}>重连</button>
          {server.operation?.status === "running" && ["connect", "test"].includes(server.operation.kind) ? <button type="button" className={compactGhostButtonClass} onClick={() => { void state.run(rpcMethods["operations.cancel"], { server_id: server.id }); }}>取消操作</button> : null}
          <button type="button" className={compactGhostButtonClass} disabled={state.busy} onClick={() => setDeleting(server.id)}>删除</button>
        </div>
        {deleting === server.id ? <div className="flex flex-wrap items-center gap-2"><span className="text-body-sm">删除 {server.label}？</span><button type="button" className={compactGhostButtonClass} disabled={state.busy} onClick={() => { void state.run(rpcMethods["servers.delete"], { server_id: server.id, expected_revision: server.revision }).then((ok) => { if (ok) { setDeleting(null); if (editing !== "new" && editing?.id === server.id) close(); } }); }}>确认删除</button><button type="button" className={compactGhostButtonClass} onClick={() => setDeleting(null)}>取消删除</button></div> : null}
      </div>
    </SettingsGroup>)}
    {snapshot && !snapshot.loading && !snapshot.error && snapshot.servers.length === 0 ? <span className="text-body-sm text-ink-muted">暂无服务器</span> : null}
  </div>;
}
