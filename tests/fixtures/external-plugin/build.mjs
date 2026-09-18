import { build } from "esbuild";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { createHash } from "node:crypto";
import { zipDirectory } from "./zip.mjs";

const root = dirname(fileURLToPath(import.meta.url));
const { values } = parseArgs({ options: { version: { type: "string", default: "1.0.0" }, variant: { type: "string", default: "valid" } } });
const version = values.version;
const variant = values.variant;
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error("Fixture version must be X.Y.Z");
if (!["valid", "incompatible", "missing-entry", "renderer-failure"].includes(variant)) throw new Error("Unknown fixture variant");
const output = resolve(root, "artifacts");
const name = `external_demo-${version}-${variant}`;
const packageRoot = resolve(output, name);
// Both components are validated above, and output is private to this fixture.
await rm(packageRoot, { recursive: true, force: true });
await mkdir(resolve(packageRoot, "backend"), { recursive: true });
await mkdir(resolve(packageRoot, "assets"), { recursive: true });
let manifest = (await readFile(resolve(root, "manifest.yaml"), "utf8")).replace(/^version: .+$/m, `version: ${version}`);
if (variant === "incompatible") manifest = manifest.replace("'>=2.1.0 <3.0.0'", "'>=99.0.0 <100.0.0'");
await writeFile(resolve(packageRoot, "manifest.yaml"), manifest, "utf8");
if (variant !== "missing-entry") {
  const source = (await readFile(resolve(root, "src/plugin.py"), "utf8")).replaceAll("__FIXTURE_VERSION__", version);
  await writeFile(resolve(packageRoot, "backend/plugin.py"), source, "utf8");
}
await copyFile(resolve(root, "src/label.txt"), resolve(packageRoot, "assets/label.txt"));
await copyFile(resolve(root, "src/style.css"), resolve(packageRoot, "style.css"));
await build({
  absWorkingDir: root,
  entryPoints: ["src/ui.tsx", "src/background.ts", "src/surface.tsx"],
  outdir: resolve(packageRoot, "renderer"),
  outExtension: { ".js": ".mjs" },
  bundle: true, format: "esm", platform: "browser", target: "es2022",
  external: ["react", "react-dom", "react/*", "react-dom/*"],
  define: { __FIXTURE_VERSION__: JSON.stringify(version), __RENDERER_FAILURE__: String(variant === "renderer-failure") },
});
const archive = resolve(output, `${name}.zip`);
await zipDirectory(packageRoot, archive);
const sha256 = createHash("sha256").update(await readFile(archive)).digest("hex");
console.log(JSON.stringify({ version, variant, packageRoot, archive, sha256 }));
