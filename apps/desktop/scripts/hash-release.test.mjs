import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { writeReleaseChecksums } from "./hash-release.mjs";

test("writeReleaseChecksums writes stable hashes and excludes itself", async () => {
  const directory = await mkdtemp(join(tmpdir(), "shiori-release-hash-"));
  try {
    await writeFile(join(directory, "b.txt"), "beta", { encoding: "utf-8" });
    await writeFile(join(directory, "a.exe"), "alpha", { encoding: "utf-8" });
    const output = await writeReleaseChecksums(directory);
    assert.match(output, /^[0-9a-f]{64}  a\.exe\n[0-9a-f]{64}  b\.txt\n$/);
    assert.equal(await readFile(join(directory, "SHA256SUMS.txt"), "utf-8"), output);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
