import type { RuntimePluginUi } from "../../../src/plugins/uiContract";
import type { PluginBridgeClient } from "./pluginBridgeClient";

/**
 * Reports one admitted renderer entry's load outcome to the backend (#262),
 * shared by the main window UI loader, the plugin-host background loader and
 * a surface window's own loader — each previously built this call, and its
 * `.catch(() => undefined)`, independently (AGENTS.md: 同一段流程出现第 2 次时
 * 就应抽成共享 helper).
 *
 * A transport failure here is distinct from the load failure the caller may
 * already have reported through its own diagnostic sink: it means the
 * backend never learned this window's outcome at all, so the plugin is left
 * showing a pending or stale state with nothing else visible anywhere. That
 * must not be silently swallowed (AGENTS.md: 业务层不要吞错) — this function
 * is still best-effort (it never lets a failed report throw into the
 * loader), but it always surfaces a transport failure through the renderer
 * diagnostic channel.
 */
export function reportRuntimePluginActivation(
  pluginBridge: Pick<PluginBridgeClient, "reportActivation">,
  entry: Pick<RuntimePluginUi, "pluginId" | "activationToken">,
  kind: "ui" | "background" | "surface",
  outcome: { ok: true } | { ok: false; reason: string },
): void {
  const activationToken = entry.activationToken ?? "";
  const report = outcome.ok ? { ok: true as const, activationToken } : { ...outcome, activationToken };
  void pluginBridge.reportActivation(entry.pluginId, kind, report).catch((transportError) => {
    window.miraDesktop?.reportRendererDiagnostic?.({
      kind: "error",
      message: `插件 ${entry.pluginId} 的 ${kind} 激活状态上报失败: ${transportError instanceof Error ? transportError.message : String(transportError)}`,
      details: { pluginId: entry.pluginId, event: `plugin-${kind}.activation-report-failed`, stage: "renderer" },
    });
  });
}

/**
 * Reports a renderer-visible load failure through the one shared diagnostic
 * shape the main window UI loader and a surface window's loader both used
 * verbatim (differing only in `event`), then reports the failure to the
 * backend (#262 AC2) via `reportRuntimePluginActivation`.
 *
 * Not used by the plugin-host background loader: that window has no
 * devtools a user could open, so its load failures go through
 * `reportBackgroundFailure` instead (which itself falls back to this same
 * `reportRendererDiagnostic` channel) — see `background/main.ts`.
 */
export function reportRuntimePluginRendererLoadFailure(
  pluginBridge: Pick<PluginBridgeClient, "reportActivation">,
  event: string,
  entry: Pick<RuntimePluginUi, "pluginId" | "activationToken">,
  kind: "ui" | "surface",
  error: unknown,
): void {
  const message = error instanceof Error ? error.message : String(error);
  window.miraDesktop.reportRendererDiagnostic({
    kind: "error",
    message,
    details: { pluginId: entry.pluginId, event, state: "FAILED", stage: "renderer" },
  });
  reportRuntimePluginActivation(pluginBridge, entry, kind, { ok: false, reason: message });
}
