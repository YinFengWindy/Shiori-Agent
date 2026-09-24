import type { PluginCategory, PluginSummary } from "./pluginBridgeClient";

/**
 * Pure presentation rules for 设置 › 插件: the name a row shows, which group
 * it sits in, its short state tag and a person-readable problem line. Raw
 * ids, diagnostic codes and error text stay in the details dialog's
 * 「开发者详情」.
 */

/** One titled group of the plugin list. */
export type PluginGroup = {
  category: PluginCategory;
  title: string;
  /** Collapsed until opened: agent-internal guards and diagnostics nobody toggles day to day. */
  collapsible: boolean;
  plugins: PluginSummary[];
};

const groupOrder: ReadonlyArray<Omit<PluginGroup, "plugins">> = [
  { category: "feature", title: "功能", collapsible: false },
  { category: "channel", title: "渠道", collapsible: false },
  { category: "system", title: "系统组件", collapsible: true },
];

/** Word-cased id for a plugin whose manifest declares no display name: `tool_loop_guard` → `Tool Loop Guard`. */
export function prettifyPluginId(id: string): string {
  return id
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => word[0]!.toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * The row title. The backend already falls back to the plugin's directory
 * name when the manifest has no `display_name`; that fallback is the raw id,
 * so it is word-cased here instead of shown verbatim.
 */
export function pluginDisplayName(plugin: Pick<PluginSummary, "id" | "name">): string {
  const name = plugin.name.trim();
  return name && name !== plugin.id ? name : prettifyPluginId(plugin.id);
}

/** Buckets the roster into 功能 / 渠道 / 系统组件, keeping roster order and dropping empty groups. */
export function groupPlugins(plugins: readonly PluginSummary[]): PluginGroup[] {
  return groupOrder
    .map((group) => ({
      ...group,
      plugins: plugins.filter((plugin) => (
        plugin.category === "system" || plugin.category === "channel" ? plugin.category : "feature"
      ) === group.category),
    }))
    .filter((group) => group.plugins.length > 0);
}

/** A short tag for a plugin that is not simply running or off; null when there is nothing to say. */
export function pluginStateLabel(plugin: PluginSummary): string | null {
  if (plugin.pendingOperation) {
    return `待重启 · ${{ install: "安装", update: "更新", uninstall: "卸载" }[plugin.pendingOperation]}`;
  }
  if (plugin.trustPendingRestart) return "待重启";
  if (plugin.state === "UNTRUSTED") return "未信任";
  if (plugin.state === "RESTART_REQUIRED") return "需要重启";
  // Backend contributions are live once setup() succeeds, but the plugin is
  // not fully ACTIVE until every declared ui/background entry has confirmed (#262 AC1).
  if (plugin.state === "ACTIVE" && plugin.pendingRendererKinds.length > 0) return "激活中…";
  return null;
}

/** Why a blocked candidate could not load, by diagnostic code. */
function blockedReason(code: string | undefined): string {
  switch (code) {
    case "missing_dependency":
      return "缺少它依赖的插件";
    case "duplicate_channel":
      return "渠道名与其他插件重复";
    case "invalid_manifest":
    case "outside_root":
      return "插件包无效";
    default:
      return "插件包没有通过检查";
  }
}

/**
 * One readable line about what went wrong, or null. An untrusted plugin is
 * not a problem (its row offers 「信任…」), and neither is one whose trust
 * is already granted and only waits for a restart.
 */
export function pluginProblem(plugin: PluginSummary): string | null {
  if (plugin.packageOperationError) return "安装或更新没有完成，已保留原来的版本";
  if (plugin.rendererError) return "界面加载失败";
  switch (plugin.state) {
    case "CONFLICT":
      return "与另一个同 ID 的插件冲突，两者都已停用";
    case "BLOCKED":
      return `无法加载：${blockedReason(plugin.diagnostic?.code)}`;
    case "FAILED":
      return "启动失败";
    case "UNTRUSTED":
      return null;
    default:
      return plugin.error && !plugin.trustPendingRestart ? "运行出错" : null;
  }
}
