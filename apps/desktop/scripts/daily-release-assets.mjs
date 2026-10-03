import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { hashReleaseFile } from "./hash-release.mjs";

/** Verifies the complete local upload set and version before any remote mutations. */
export async function readDailyAssets(directory, version) {
  const names = (await readdir(directory, { withFileTypes: true }))
    .filter((entry) => entry.isFile()).map((entry) => entry.name).sort();
  for (const required of ["latest.yml", "SHA256SUMS.txt"]) {
    if (!names.includes(required)) throw new Error(`Missing release file: ${required}`);
  }
  if (!names.some((name) => name.endsWith(".exe")) || !names.some((name) => name.endsWith(".blockmap"))) {
    throw new Error("Missing Windows installer or update blockmap");
  }
  const metadata = await readFile(join(directory, "latest.yml"), "utf8");
  if (!metadata.split(/\r?\n/).includes(`version: ${version}`)) {
    throw new Error(`Update metadata version does not match ${version}`);
  }
  const checksums = new Map();
  for (const line of (await readFile(join(directory, "SHA256SUMS.txt"), "utf8")).trim().split(/\r?\n/)) {
    const match = /^([a-f0-9]{64})  (.+)$/.exec(line);
    if (!match || checksums.has(match[2])) throw new Error(`Invalid checksum line: ${line}`);
    checksums.set(match[2], match[1]);
  }
  if (checksums.size !== names.length - 1) throw new Error("Incomplete release checksums");
  const files = [];
  for (const name of names) {
    const path = join(directory, name);
    const digest = await hashReleaseFile(path);
    if (name !== "SHA256SUMS.txt" && checksums.get(name) !== digest) {
      throw new Error(`Checksum mismatch: ${name}`);
    }
    files.push({ name, path, digest: `sha256:${digest}`, size: (await stat(path)).size });
  }
  return files;
}

/** Requires every GitHub asset to be uploaded with the same size and SHA-256. */
export function verifyDailyAssets(files, assets) {
  if (assets.length !== files.length) throw new Error("Incomplete remote release assets");
  for (const file of files) {
    const matches = assets.filter((asset) => asset.name === file.name);
    if (matches.length !== 1 || matches[0].state !== "uploaded"
      || matches[0].size !== file.size || matches[0].digest !== file.digest) {
      throw new Error(`Remote asset verification failed: ${file.name}`);
    }
  }
}
