import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import { InlineError } from "../shared/feedback/InlineError";
import { useConfiguredMemoryPlugin } from "./useConfiguredMemoryPlugin";

/** Hosts only the configured memory plugin's role-detail contribution. */
export function RoleMemoryPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  const selection = useConfiguredMemoryPlugin(bridgeReady);
  const isPluginEnabled = usePluginEnabledState();
  const panel = selection.status === "ready"
    ? pluginUiRegistry.getRoleMemoryPanel(selection.pluginId, isPluginEnabled)
    : undefined;

  if (!bridgeReady) return <p role="status" className="text-body-sm text-ink-muted">连接已断开</p>;
  if (selection.status === "loading") return <p role="status" className="text-body-sm text-ink-muted">加载中…</p>;
  if (selection.status === "error") return <InlineError message={`记忆设置读取失败：${selection.error}`} />;
  if (!panel) return <p role="status" className="text-body-sm text-ink-muted">记忆插件不可用</p>;
  return <panel.Component key={`${panel.id}:${roleId}`} roleId={roleId} bridgeReady={bridgeReady} />;
}
