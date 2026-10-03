import type { PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { applyPluginBackgroundModules } from "./pluginBackgroundContract";

/**
 * Compiles every plugin's headless background entry point into the
 * `plugin-host.html` bundle — the dedicated hidden renderer window that owns
 * a plugin's always-resident orchestration code (#226 item 1, unblocking
 * #181-C).
 *
 * `import.meta.glob` is a Vite build-time macro, matching the model #174
 * chose (`#213` tracks moving to runtime loading later) and the same
 * mechanism `pluginUiModules.ts` and `pluginSurfaceModules.ts` already use.
 * Like those two, this file cannot be exercised by the plain node:test/tsx
 * runner used everywhere else, and `pnpm run build` alone does not prove the
 * glob resolves — with no `plugins/<id>/background/` directory in the repo it
 * matches nothing and the build succeeds regardless. It is proven by
 * `apps/desktop/scripts/test-plugin-ui-build-smoke.mjs`, which writes a
 * throwaway plugin background entry with a marker, runs a real build, and
 * asserts the marker landed in the `plugin-host` bundle specifically. The
 * registration logic this file delegates to is unit tested separately in
 * `pluginBackgroundContract.test.ts`.
 */
const modules = import.meta.glob<{ default: PluginBackgroundContribution }>(
  "/../../../plugins/*/background/index.ts",
  { eager: true },
);

applyPluginBackgroundModules(modules);
