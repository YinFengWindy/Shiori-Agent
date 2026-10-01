import { errorMessage } from "@shiori/plugin-sdk";

/**
 * Reports a plugin-host failure somewhere a human will actually find it.
 *
 * The plugin-host window is never shown and has no devtools a user would open,
 * so a bare `console.error` here is the same as silence — and the failures that
 * land here are the interesting ones: a plugin's `setup(ctx)` throwing, a
 * teardown leaking, a command the user just issued from the tray not working.
 * Before #181-C the equivalent failures went through `logDesktopDiagnostic` in
 * the main process, and losing that would have been a net regression from
 * moving this code into a renderer.
 *
 * Still logs to the console as well: during `pnpm run desktop:dev` the devtools
 * console is the faster loop.
 */
export function reportBackgroundFailure(what: string, error: unknown): void {
  const normalized = error instanceof Error ? error : new Error(String(error));
  console.error(`[plugin-host] ${what} 失败`, normalized);
  // `typeof window`, not `window?.` — an undeclared identifier throws a
  // ReferenceError rather than evaluating to undefined, and the plugin-host
  // code this reports for is unit tested under the plain node runner, which has
  // no DOM. A diagnostics helper that throws inside a failure path would turn
  // every reported failure into a second, more confusing one.
  if (typeof window === "undefined") return;
  window.miraDesktop?.reportRendererDiagnostic?.({
    kind: "error",
    message: `[plugin-host] ${what} 失败: ${errorMessage(error, { includeDetail: true })}`,
    stack: normalized.stack,
  });
}
