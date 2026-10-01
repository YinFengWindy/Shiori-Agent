/** Synchronize npm metadata from the Python SDK's single version source. */
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const sdk = new URL("../packages/sdk/", import.meta.url);
const source = await readFile(new URL("python/shiori_sdk/_version.py", sdk), "utf8");
const version = source.match(/^__version__ = "([^"]+)"$/m)?.[1];
if (!version) throw new Error("Missing SDK version source");
const manifestPath = new URL("package.json", sdk);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
if (manifest.version !== version) {
  if (process.argv.includes("--check")) {
    throw new Error(`SDK versions differ: npm ${manifest.version}, Python ${version}. Run node scripts/sync_sdk_version.mjs.`);
  }
  manifest.version = version;
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}
console.log(`SDK version ${version}: ${fileURLToPath(sdk)}`);
