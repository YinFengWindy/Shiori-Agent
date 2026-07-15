/// <reference types="node" />

import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";
import { LocalAssetRegistry } from "./localAssetRegistry";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function createTemporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "shiori-local-assets-"));
  temporaryDirectories.push(directory);
  return directory;
}

describe("LocalAssetRegistry", () => {
  it("resolves only exact paths granted by a trusted boundary", async () => {
    const directory = await createTemporaryDirectory();
    const grantedPath = join(directory, "avatar.png");
    const deniedPath = join(directory, "private.png");
    await writeFile(grantedPath, Buffer.from("granted"));
    await writeFile(deniedPath, Buffer.from("denied"));
    const registry = new LocalAssetRegistry();

    const reference = registry.grantPath(grantedPath);

    assert.ok(reference);
    assert.equal(reference.kind, "image");
    assert.match(reference.url, /^mira-asset:\/\/local\/[0-9a-f-]+$/);
    assert.equal(registry.resolveReference(reference.url)?.canonicalPath, grantedPath);
    assert.equal(registry.resolveReference(grantedPath)?.canonicalPath, grantedPath);
    assert.equal(registry.resolveReference(deniedPath), null);
    assert.equal(
      registry.resolveUrl(`mira-asset://local?path=${encodeURIComponent(deniedPath)}`),
      null,
    );
  });

  it("grants only known asset fields from bridge payloads", async () => {
    const directory = await createTemporaryDirectory();
    const managedDirectory = join(directory, "workspace");
    const externalDirectory = join(directory, "external");
    await mkdir(managedDirectory);
    await mkdir(externalDirectory);
    const avatarPath = join(managedDirectory, "avatar.png");
    const arbitraryPath = join(managedDirectory, "arbitrary.png");
    const documentPath = join(managedDirectory, "note.md");
    const launderedPath = join(externalDirectory, "laundered.txt");
    await writeFile(avatarPath, Buffer.from("avatar"));
    await writeFile(arbitraryPath, Buffer.from("arbitrary"));
    await writeFile(documentPath, "note", "utf-8");
    await writeFile(launderedPath, "secret", "utf-8");
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(managedDirectory);

    registry.grantTrustedPayload({
      role: { avatar_abs: avatarPath, arbitrary: arbitraryPath },
      session: { media: [documentPath, launderedPath] },
    });

    assert.equal(registry.resolveReference(avatarPath)?.kind, "image");
    assert.equal(registry.resolveReference(documentPath)?.kind, "document");
    assert.equal(registry.resolveReference(arbitraryPath), null);
    assert.equal(registry.resolveReference(launderedPath), null);
  });

  it("keeps picker-granted external paths authorized when bridge echoes them", async () => {
    const directory = await createTemporaryDirectory();
    const externalPath = join(directory, "picked.txt");
    await writeFile(externalPath, "picked", "utf-8");
    const registry = new LocalAssetRegistry();

    registry.grantPath(externalPath);
    registry.grantTrustedPayload({ session: { media: [externalPath] } });

    assert.equal(registry.resolveReference(externalPath)?.kind, "document");
  });

  it("rejects relative, unsupported, missing, and non-file paths", async () => {
    const directory = await createTemporaryDirectory();
    const unsupportedPath = join(directory, "archive.json");
    const imageDirectory = join(directory, "folder.png");
    await writeFile(unsupportedPath, "{}", "utf-8");
    await mkdir(imageDirectory);
    const registry = new LocalAssetRegistry();

    assert.equal(registry.grantPath("relative.png"), null);
    assert.equal(registry.grantPath(unsupportedPath), null);
    assert.equal(registry.grantPath(join(directory, "missing.png")), null);
    assert.equal(registry.grantPath(imageDirectory), null);
    assert.equal(registry.resolveReference("\\\\server\\share\\secret.txt"), null);
  });
});
