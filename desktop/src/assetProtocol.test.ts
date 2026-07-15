/// <reference types="node" />

import assert from "node:assert/strict";
import { mkdtemp, rm, symlink, truncate, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";
import {
  loadGrantedLocalAsset,
  localAssetSchemePrivileges,
  registerLocalAssetProtocol,
} from "./assetProtocol";
import { LocalAssetRegistry, maxLocalAssetBytes } from "./localAssetRegistry";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

async function createTemporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "shiori-asset-protocol-"));
  temporaryDirectories.push(directory);
  return directory;
}

describe("local asset protocol", () => {
  it("serves an authorized image with hardened response headers", async () => {
    const directory = await createTemporaryDirectory();
    const imagePath = join(directory, "avatar.PNG");
    await writeFile(imagePath, Buffer.from("image-bytes"));
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const reference = registry.grantPath(imagePath);
    assert.ok(reference);

    const response = await loadGrantedLocalAsset(registry, reference.url);
    const legacyResponse = await loadGrantedLocalAsset(
      registry,
      `mira-asset://local?path=${encodeURIComponent(imagePath)}`,
    );
    const tokenWithLegacyQuery = await loadGrantedLocalAsset(
      registry,
      `${reference.url}?path=${encodeURIComponent(imagePath)}`,
    );

    assert.equal(response.status, 200);
    assert.equal(legacyResponse.status, 403);
    assert.equal(tokenWithLegacyQuery.status, 403);
    assert.equal(response.headers.get("Content-Type"), "image/png");
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
    assert.equal(await response.text(), "image-bytes");
  });

  it("denies ungranted paths and refuses to render authorized documents", async () => {
    const directory = await createTemporaryDirectory();
    const imagePath = join(directory, "private.png");
    const documentPath = join(directory, "note.txt");
    await writeFile(imagePath, Buffer.from("private"));
    await writeFile(documentPath, "note", "utf-8");
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const documentReference = registry.grantPath(documentPath);
    assert.ok(documentReference);

    const denied = await loadGrantedLocalAsset(
      registry,
      `mira-asset://local?path=${encodeURIComponent(imagePath)}`,
    );
    const document = await loadGrantedLocalAsset(registry, documentReference.url);

    assert.equal(denied.status, 403);
    assert.equal(document.status, 415);
  });

  it("rejects authorized images above the size limit before reading them", async () => {
    const directory = await createTemporaryDirectory();
    const imagePath = join(directory, "large.webp");
    await writeFile(imagePath, "", "utf-8");
    await truncate(imagePath, maxLocalAssetBytes + 1);
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const reference = registry.grantPath(imagePath);
    assert.ok(reference);

    const response = await loadGrantedLocalAsset(registry, reference.url);

    assert.equal(response.status, 413);
  });

  it("returns 404 when an authorized image disappears", async () => {
    const directory = await createTemporaryDirectory();
    const imagePath = join(directory, "missing.png");
    await writeFile(imagePath, Buffer.from("image"));
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const reference = registry.grantPath(imagePath);
    assert.ok(reference);
    await unlink(imagePath);

    const response = await loadGrantedLocalAsset(registry, reference.url);

    assert.equal(response.status, 404);
  });

  it("rejects a symlink grant after the link target changes", async (testContext) => {
    const directory = await createTemporaryDirectory();
    const firstTarget = join(directory, "first.png");
    const secondTarget = join(directory, "second.png");
    const linkPath = join(directory, "linked.png");
    await writeFile(firstTarget, Buffer.from("first"));
    await writeFile(secondTarget, Buffer.from("second"));
    try {
      await symlink(firstTarget, linkPath, "file");
    } catch (error) {
      if (["EPERM", "EACCES"].includes((error as NodeJS.ErrnoException).code ?? "")) {
        testContext.skip("file symlinks are unavailable in this Windows environment");
        return;
      }
      throw error;
    }
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const reference = registry.grantPath(linkPath);
    assert.ok(reference);
    await unlink(linkPath);
    await symlink(secondTarget, linkPath, "file");

    const response = await loadGrantedLocalAsset(registry, reference.url);

    assert.equal(response.status, 403);
  });

  it("registers the handler without granting Fetch or CORS privileges", () => {
    const registry = new LocalAssetRegistry();
    let scheme = "";
    let handler: ((request: { url: string }) => Promise<Response> | Response) | null = null;

    registerLocalAssetProtocol({
      handle(nextScheme, nextHandler) {
        scheme = nextScheme;
        handler = nextHandler;
      },
    }, registry);

    assert.equal(scheme, "mira-asset");
    assert.equal(typeof handler, "function");
    assert.deepEqual(localAssetSchemePrivileges, { standard: true, secure: true });
    assert.equal("supportFetchAPI" in localAssetSchemePrivileges, false);
    assert.equal("corsEnabled" in localAssetSchemePrivileges, false);
  });
});
