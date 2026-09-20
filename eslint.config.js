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

export default desktopEslintConfig([
  "apps/desktop/tests/plugin-ui/packaged*.ts",
  "tests/fixtures/external-plugin/src/**/*.ts",
  "tests/fixtures/external-plugin/src/**/*.tsx",
  "apps/desktop/src/**/*.ts",
  "apps/desktop/src/**/*.tsx",
  "apps/desktop/renderer/src/**/*.ts",
  "apps/desktop/renderer/src/**/*.tsx",
  "apps/desktop/showcase/**/*.ts",
  "plugins/*/ui/**/*.ts",
  "plugins/*/ui/**/*.tsx",
  "plugins/*/surface/**/*.ts",
  "plugins/*/surface/**/*.tsx",
  "plugins/*/background/**/*.ts",
  "plugins/*/background/**/*.tsx",
]);
