import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { readDailyAssets, verifyDailyAssets } from "./daily-release-assets.mjs";
import { writeReleaseChecksums } from "./hash-release.mjs";

const installerName = "Shiori-Setup-0.5.1.exe";

async function artifacts(t, installer = installerName) {
  const directory = await mkdtemp(join(tmpdir(), "shiori-assets-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  for (const [name, body] of [
    [installer, "installer"], [`${installer}.blockmap`, "blockmap"],
    ["latest.yml", `version: 0.5.1\npath: ${installer}\n`],
  ]) await writeFile(join(directory, name), body, "utf8");
  await writeReleaseChecksums(directory);
  return directory;
}

test("all installer, updater and checksum files are verified before upload", async (t) => {
  const files = await readDailyAssets(await artifacts(t), "0.5.1");
  assert.equal(files.length, 4);
  assert.ok(files.every((file) => /^sha256:[a-f0-9]{64}$/.test(file.digest)));
  verifyDailyAssets(files, files.map((file) => ({ ...file, state: "uploaded" })));
});

test("version mismatch, tampering and incomplete checksum manifests stop publication", async (t) => {
  const directory = await artifacts(t);
  await assert.rejects(readDailyAssets(directory, "0.5.2"), /metadata version/);
  await writeFile(join(directory, installerName), "changed", "utf8");
  await assert.rejects(readDailyAssets(directory, "0.5.1"), /Checksum mismatch/);
  await writeReleaseChecksums(directory);
  await writeFile(join(directory, "extra.txt"), "unhashed", "utf8");
  await assert.rejects(readDailyAssets(directory, "0.5.1"), /Incomplete release checksums/);
});

test("missing installer, blockmap or required files fails closed", async (t) => {
  const directory = await artifacts(t);
  await rm(join(directory, `${installerName}.blockmap`));
  await assert.rejects(readDailyAssets(directory, "0.5.1"), /Missing Windows/);
  await rm(join(directory, "latest.yml"));
  await assert.rejects(readDailyAssets(directory, "0.5.1"), /Missing release file/);
});

test("remote upload completeness, state, size and hash are all required", () => {
  const file = { name: "installer.exe", size: 3, digest: "sha256:abc" };
  const valid = { ...file, state: "uploaded" };
  for (const assets of [[], [valid, valid], [{ ...valid, state: "starter" }],
    [{ ...valid, size: 4 }], [{ ...valid, digest: "sha256:other" }]]) {
    assert.throws(() => verifyDailyAssets([file], assets), /release assets|verification failed/);
  }
});

test("legacy installer names are rejected before GitHub can rename them and break metadata", async (t) => {
  const legacyName = "Shiori Setup 0.5.1.exe";
  const directory = await artifacts(t, legacyName);
  await assert.rejects(readDailyAssets(directory, "0.5.1"), /filename is not GitHub-safe/);
  // GitHub's real asset shape uses hyphens; softprops may retain the old name
  // only as a display label, which cannot repair updater/checksum references.
  const local = { name: legacyName, size: 9, digest: "sha256:installer" };
  const remote = { ...local, name: installerName, label: legacyName, state: "uploaded" };
  assert.throws(() => verifyDailyAssets([local], [remote]), /verification failed/);
  verifyDailyAssets([{ ...local, name: installerName }], [remote]);
});
