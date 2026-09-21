import { copyFile, mkdir, mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { digest, downloadVerified, exists, extractZip } from "./native-runtime.mjs";
import { resolveReleaseManifest } from "./release-manifest.mjs";

/** Installs only the pinned standalone Driver and UIA helper, with MIT notices. */
export async function prepareComputerRuntime({ repositoryRoot, targetPlatform = process.platform,
  targetArch = process.arch, download = fetch, extract = extractZip } = {}) {
  if (targetPlatform !== "win32" || targetArch !== "x64") {
    throw new Error("Computer runtime preparation requires Windows x64");
  }
  const plugin = join(repositoryRoot, "plugins", "computer_use");
  const manifest = JSON.parse(await readFile(join(plugin, "native-runtime.json"), "utf8"));
  const root = join(repositoryRoot, "native", "computer-use");
  const cache = join(repositoryRoot, "native", ".downloads");
  await mkdir(root, { recursive: true });
  await mkdir(cache, { recursive: true });
  const archive = join(cache, `cua-driver-${manifest.driver.version}-win32-x64.zip`);
  await downloadVerified(manifest.driver, archive, download);
  const complete = await Promise.all(Object.entries(manifest.files).map(async ([name, hash]) =>
    await exists(join(root, name)) && digest(await readFile(join(root, name))) === hash));
  if (!complete.every(Boolean)) {
    const staging = await mkdtemp(join(cache, "cua-extract-"));
    try {
      await extract(archive, staging, repositoryRoot);
      for (const [name, hash] of Object.entries(manifest.files)) {
        if (digest(await readFile(join(staging, name))) !== hash) {
          throw new Error(`Computer runtime extracted SHA256 mismatch: ${name}`);
        }
      }
      for (const name of Object.keys(manifest.files)) await copyFile(join(staging, name), join(root, name));
    } finally {
      await rm(staging, { recursive: true, force: true });
    }
  }
  for (const name of ["native-runtime.json", "LICENSE.cua-driver"]) {
    await copyFile(join(plugin, name), join(root, name));
  }
  return root;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = await prepareComputerRuntime({ repositoryRoot: resolveReleaseManifest().repositoryRoot });
  console.log(`Computer Use runtime ready: ${root}`);
}
