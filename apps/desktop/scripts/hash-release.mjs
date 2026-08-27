import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { resolveReleaseManifest } from "./release-manifest.mjs";

async function sha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) {
    hash.update(chunk);
  }
  return hash.digest("hex");
}

/** Writes deterministic SHA-256 checksums for all release files except the checksum file itself. */
export async function writeReleaseChecksums(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = entries
    .filter((entry) => entry.isFile() && entry.name !== "SHA256SUMS.txt")
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right));
  const lines = [];
  for (const name of files) {
    lines.push(`${await sha256(join(directory, name))}  ${name}`);
  }
  const output = `${lines.join("\n")}\n`;
  await writeFile(join(directory, "SHA256SUMS.txt"), output, { encoding: "utf-8" });
  return output;
}

const invokedDirectly = process.argv[1]?.endsWith("hash-release.mjs");
if (invokedDirectly) {
  await writeReleaseChecksums(resolveReleaseManifest().installerOutput);
}
