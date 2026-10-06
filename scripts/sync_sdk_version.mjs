/** Synchronize SDK package metadata and exact host pins from one Python version literal. */
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** Check all consumers before writing, without importing SDK source into host packaging. */
export async function syncSdkVersion(repositoryRoot, { check = false } = {}) {
  const source = await readFile(join(repositoryRoot, "packages/sdk/python/shiori_sdk/_version.py"), "utf8");
  const version = source.match(/^__version__ = "([^"]+)"$/m)?.[1];
  if (!version) throw new Error("Missing SDK version source");
  const files = [
    { path: "packages/sdk/package.json" },
    { path: "setup.py", pattern: /("shiori-sdk==)([^"\r\n]+)(")/g },
    { path: "packages/shiori-host-testing/pyproject.toml", pattern: /("shiori-sdk\[testing\]==)([^"\r\n]+)(")/g },
  ];
  const contents = await Promise.all(files.map(({ path }) => readFile(join(repositoryRoot, path), "utf8")));
  const changes = files.flatMap(({ path, pattern }, index) => {
    const content = contents[index];
    let current, updated;
    if (pattern) {
      const matches = [...content.matchAll(pattern)];
      if (matches.length !== 1) throw new Error(`Expected exactly one SDK version pin in ${path}`);
      current = matches[0][2];
      updated = content.replace(pattern, (_match, prefix, _previous, suffix) => `${prefix}${version}${suffix}`);
    } else {
      const manifest = JSON.parse(content);
      current = manifest.version;
      updated = `${JSON.stringify({ ...manifest, version }, null, 2)}\n`;
    }
    return current === version ? [] : [{ path, current, updated }];
  });
  if (check && changes.length) {
    throw new Error(`SDK versions differ from Python ${version}: ${changes.map(({ path, current }) => `${path} (${current})`).join(", ")}. Run node scripts/sync_sdk_version.mjs.`);
  }
  for (const { path, updated } of changes) await writeFile(join(repositoryRoot, path), updated, "utf8");
  return version;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const repositoryRoot = fileURLToPath(new URL("../", import.meta.url));
  const version = await syncSdkVersion(repositoryRoot, { check: process.argv.includes("--check") });
  console.log(`SDK version ${version}: ${join(repositoryRoot, "packages/sdk")}`);
}
