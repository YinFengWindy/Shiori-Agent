// Repository-root ESLint configuration.
//
// It exists because ESLint resolves what is lintable from the working
// directory: an ESLint run rooted at `apps/desktop/` refuses to lint anything
// above it, including the colocated plugin UI under the top-level `plugins/`
// tree that is compiled straight into the renderer bundle (#174, #181). Moving
// plugin-owned renderer code out of `apps/desktop/renderer/src/` without this
// would silently drop it from lint.
//
// The rules themselves stay next to the toolchain that provides them —
// `typescript-eslint` and the React plugins live in `apps/desktop/node_modules`,
// and are resolved from that file rather than from here.
import { desktopEslintConfig } from "./apps/desktop/eslint.config.js";

/**
 * Plugin renderer code (including `shared/` modules the renderer entries import)
 * and the plugin SDK. Plugins reach the host only
 * through `@yinfengwindy/shiori-sdk` and their injected `client`/`host` (#440), and
 * the SDK itself must never depend on host source.
 */
const pluginRendererFiles = [
  "plugins/*/ui/**/*.ts",
  "plugins/*/ui/**/*.tsx",
  "plugins/*/surface/**/*.ts",
  "plugins/*/surface/**/*.tsx",
  "plugins/*/background/**/*.ts",
  "plugins/*/background/**/*.tsx",
  "plugins/*/shared/**/*.ts",
  "plugins/*/shared/**/*.tsx",
  "packages/sdk/src/**/*.ts",
  "packages/sdk/src/**/*.tsx",
];

const hostImportMessage = "Plugins must not import host source (apps/desktop); use @yinfengwindy/shiori-sdk or the injected client/host.";
const hostInternalMessage = "@yinfengwindy/shiori-sdk/host-internal is host-only and not part of the plugin contract; use the @yinfengwindy/shiori-sdk main entry.";

export default [
  ...desktopEslintConfig([
    "apps/desktop/tests/plugin-ui/packaged*.ts",
    "apps/desktop/tests/plugin-ui/distribution*.ts",
    "tests/fixtures/external-plugin/src/**/*.ts",
    "tests/fixtures/external-plugin/src/**/*.tsx",
    "apps/desktop/src/**/*.ts",
    "apps/desktop/src/**/*.tsx",
    "apps/desktop/renderer/src/**/*.ts",
    "apps/desktop/renderer/src/**/*.tsx",
    // The public site (#769). Its .astro files are checked by `astro check`
    // (root `pnpm typecheck`), not by ESLint.
    "apps/site/*.ts",
    "apps/site/src/**/*.ts",
    "apps/site/src/**/*.tsx",
    "apps/site/tests/**/*.ts",
    ...pluginRendererFiles,
  ]),
  {
    files: pluginRendererFiles,
    rules: {
      "no-restricted-syntax": ["error", {
        selector: "Identifier[name='miraDesktop'], Literal[value='miraDesktop'], Identifier[name='DesktopApi']",
        message: "Plugins must not access the host global bridge or ambient DesktopApi; use injected SDK capabilities.",
      }],
      "no-restricted-imports": ["error", {
        patterns: [
          // Any relative (`../../../apps/desktop/...`) or aliased spelling that names the host tree.
          { regex: "(^|/)apps/desktop(/|$)", message: hostImportMessage },
          // SDK internals the host shares with the SDK; not in the peer ABI, so a plugin could not load them anyway.
          { regex: "^@yinfengwindy/shiori-sdk/host-internal$", message: hostInternalMessage },
        ],
      }],
    },
  },
];
