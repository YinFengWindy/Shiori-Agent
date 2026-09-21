import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { downloadVerified, exists, extractZip } from "./native-runtime.mjs";
import { fileURLToPath } from "node:url";
import { resolveReleaseManifest } from "./release-manifest.mjs";

/** Prepares pinned Windows components; never downloads or runs them on other platforms. */
export async function prepareBrowserRuntime({ repositoryRoot, targetPlatform = process.platform,
  download = fetch, extract = extractZip } = {}) {
  if (targetPlatform !== "win32") throw new Error("Browser runtime preparation requires Windows x64");
  const plugin = join(repositoryRoot, "plugins", "browser_use");
  const manifestText = await readFile(join(plugin, "native-runtime.json"), "utf8");
  const manifest = JSON.parse(manifestText);
  const root = join(repositoryRoot, "native", "browser-use");
  const cache = join(repositoryRoot, "native", ".downloads");
  await mkdir(root, { recursive: true });
  await mkdir(cache, { recursive: true });
  await downloadVerified(manifest.agentBrowser, join(root, "agent-browser.exe"), download);
  const chromeArchive = join(cache, `chrome-${manifest.chrome.version}.zip`);
  await downloadVerified(manifest.chrome, chromeArchive, download);
  const stamp = join(root, "chrome.sha256");
  const current = await exists(stamp) ? await readFile(stamp, "utf8") : "";
  if (current !== manifest.chrome.sha256 || !(await exists(join(root, "chrome-win64", "chrome.exe")))) {
    // Only this generated directory is replaced; user profiles live in workspace.
    await rm(join(root, "chrome-win64"), { recursive: true, force: true });
    await extract(chromeArchive, root, repositoryRoot);
    await writeFile(stamp, manifest.chrome.sha256, "utf8");
  }
  for (const name of ["native-runtime.json", "LICENSE.agent-browser"]) {
    await copyFile(join(plugin, name), join(root, name));
  }
  for (const name of ["chrome-win64/chrome.exe", "chrome-win64/ABOUT"]) {
    if (!(await exists(join(root, name)))) throw new Error(`Incomplete browser runtime: ${name}`);
  }
  return root;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = await prepareBrowserRuntime({ repositoryRoot: resolveReleaseManifest().repositoryRoot });
  console.log(`Browser Use runtime ready: ${root}`);
}
