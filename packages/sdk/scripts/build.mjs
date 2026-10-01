/** Build standalone ESM entries with shared chunks and external peer dependencies. */
import { build } from "esbuild";

await build({
  entryPoints: { index: "src/index.ts", contract: "src/contract.ts", hostInternal: "src/hostInternal.ts", "testing/index": "src/testing/index.ts" },
  outdir: "dist",
  bundle: true,
  splitting: true,
  format: "esm",
  packages: "external",
  platform: "neutral",
  target: "es2022",
  jsx: "automatic",
});
