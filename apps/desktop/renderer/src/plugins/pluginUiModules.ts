import { applyPluginUiModules, type PluginUiModule } from "./pluginUiModuleContract";

/**
 * Compiles every plugin's UI entry point straight into the renderer bundle
 * (no runtime dynamic import of third-party code, per the issue #174
 * decision). `import.meta.glob` is a Vite build-time macro: it cannot be
 * exercised by the plain node:test/tsx unit test runner this repo uses for
 * everything else, so this file has no unit test of its own.
 *
 * The glob's path resolution and bundling are also proven by
 * `apps/desktop/scripts/test-plugin-ui-build-smoke.mjs` (run via
 * `pnpm run desktop:test:plugin-ui` from the repo root), which writes a
 * throwaway `plugins/<id>/ui/index.tsx` with a marker string, runs a real
 * renderer build, asserts the marker landed in the bundled output, and
 * removes the throwaway plugin afterwards.
 *
 * The merge logic this file delegates to (`applyPluginUiModules`) is
 * separately unit tested against a hand-built module record in
 * `pluginUiModuleContract.test.ts`. See the Testing Decisions section of
 * docs/specs/2026-09-09-issue-174-plugin-system-restructure.md.
 */
const modules = import.meta.glob<{ default: PluginUiModule }>(
  "/../../../plugins/*/ui/index.tsx",
  { eager: true },
);

applyPluginUiModules(modules);
