import { createHash } from "node:crypto";
import { readFile, rename, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

/** Returns a lowercase SHA256 digest of downloaded or installed bytes. */
export const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");

/** Tests for a regular file while retaining permission and filesystem errors. */
export async function exists(path) {
  try { return (await stat(path)).isFile(); }
  catch (error) { if (error.code === "ENOENT") return false; throw error; }
}

/** Reuses matching assets and verifies downloads before installing them. */
export async function downloadVerified(asset, path, download) {
  if (await exists(path) && digest(await readFile(path)) === asset.sha256) return;
  const response = await download(asset.url);
  if (!response.ok) throw new Error(`Native runtime download failed: ${response.status} ${asset.url}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (digest(bytes) !== asset.sha256) throw new Error(`Native runtime SHA256 mismatch: ${asset.url}`);
  await writeFile(`${path}.part`, bytes);
  await rename(`${path}.part`, path);
}

/** Extracts an archive with this checkout's Python, without system runtimes. */
export function extractZip(archive, destination, repositoryRoot) {
  const python = join(repositoryRoot, ".venv", "Scripts", "python.exe");
  const result = spawnSync(python, ["-m", "zipfile", "-e", archive, destination], { encoding: "utf8", windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`Native archive extraction failed: ${result.stderr}`);
}
