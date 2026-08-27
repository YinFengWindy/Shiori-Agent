import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { resolveReleaseManifest } from "./release-manifest.mjs";

test("resolveReleaseManifest keeps build and installer outputs explicit", async () => {
  const directory = await mkdtemp(join(tmpdir(), "shiori-release-manifest-"));
  try {
    const manifest = resolveReleaseManifest({ releaseOutput: join(directory, "installer") });

    assert.equal(manifest.backendRoot, resolve(manifest.repositoryRoot, "apps/backend"));
    assert.equal(manifest.releaseBuildRoot, resolve(manifest.repositoryRoot, "release"));
    assert.equal(manifest.runtimeOutput, resolve(manifest.releaseBuildRoot, "runtime"));
    assert.equal(manifest.pyinstallerWork, resolve(manifest.releaseBuildRoot, "pyinstaller-work"));
    assert.equal(manifest.installerOutput, resolve(directory, "installer"));
    assert.equal(manifest.unpackedOutput, resolve(directory, "installer/win-unpacked"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
