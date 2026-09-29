import type { PluginSurfaceModule } from "@shiori/plugin-sdk";
import { applyPluginSurfaceModules } from "./pluginSurfaceContract";

/**
 * Compiles every plugin's desktop-surface entry point into the shared
 * `surface.html` bundle.
 *
 * `import.meta.glob` is a Vite build-time macro, so this is still the
 * build-time model #174 chose; #213 tracks moving to runtime loading. What it
 * removes is the *per-plugin* build coupling: before this, owning a desktop
 * window meant adding an HTML entry to `renderer/vite.config.ts` by hand (see
 * the pet's `pet.html`). Now one host-owned entry serves every plugin, told
 * which one to mount through its query string.
 *
 * Like `pluginUiModules.ts`, the glob itself cannot be exercised by the plain
 * node:test/tsx runner used everywhere else, and `pnpm run build` alone does
 * not prove it either — with no `plugins/<id>/surface/` directory in the repo
 * the glob matches nothing and the build succeeds regardless. It is proven by
 * `apps/desktop/scripts/test-plugin-ui-build-smoke.mjs`, which writes a
 * throwaway plugin surface with a marker, runs a real build, and asserts the
 * marker landed in the bundle. The registration logic this file delegates to
 * is unit tested separately in `pluginSurfaceContract.test.ts`.
 */
const modules = import.meta.glob<{ default: PluginSurfaceModule }>(
  "/../../../plugins/*/surface/index.tsx",
  { eager: true },
);

applyPluginSurfaceModules(modules);
