/**
 * Dependencies `bootstrapSurfaceWindow` needs, injected so its branches are
 * unit-testable without Electron, React DOM or a real bridge connection.
 */
export type SurfaceBootstrapDeps = {
  /** Evaluates the build-time plugin surface glob; only success/failure matters here. */
  loadGlobModules: () => Promise<unknown>;
  /** Loads this window's own plugin's runtime `renderer.surface` entry, if any. */
  loadOwnRuntimeSurface: () => Promise<void>;
  /** Renders the glob-failure card. */
  renderFailure: (detail: string) => void;
  /** Renders the real surface content once loading (glob and runtime) has been attempted. */
  renderSurface: () => void;
  /** Logs an error from either step; both steps are otherwise isolated from each other. */
  onError?: (scope: "glob" | "runtime", error: unknown) => void;
};

/**
 * Drives one surface window's startup: evaluate the built-in plugin glob,
 * attempt this window's own runtime surface entry, then always render.
 *
 * Extracted from `main.tsx` (#262) so its branches — glob failure, runtime
 * entry failure, success — are unit-testable with injected dependencies
 * instead of only reachable through a real Electron/React DOM boot, which is
 * exactly why an unguarded `await` on `plugins.list` inside the runtime step
 * during Phase A slipped through undetected (a surface window stays
 * `show: false` until it renders — see #222 — so that bug left the window
 * permanently hidden with no explanation).
 *
 * A glob failure renders the failure card and stops: the built-in registry
 * did not evaluate, so nothing later can be trusted to know what plugin owns
 * this window. A runtime entry failure is isolated to that step alone —
 * `loadOwnRuntimeSurface` already reports it through the renderer diagnostic
 * and backend activation-report paths — and must still let `renderSurface`
 * run, so the window shows its existing "this plugin registered nothing"
 * card instead of staying hidden forever.
 */
export async function bootstrapSurfaceWindow(deps: SurfaceBootstrapDeps): Promise<void> {
  try {
    await deps.loadGlobModules();
  } catch (error) {
    deps.onError?.("glob", error);
    deps.renderFailure("插件模块加载失败");
    return;
  }
  try {
    await deps.loadOwnRuntimeSurface();
  } catch (error) {
    deps.onError?.("runtime", error);
  }
  deps.renderSurface();
}
