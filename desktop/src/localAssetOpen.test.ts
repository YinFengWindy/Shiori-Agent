/// <reference types="node" />

import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, it } from "node:test";
import { openGrantedLocalAsset } from "./localAssetOpen";
import { LocalAssetRegistry } from "./localAssetRegistry";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => rm(path, { recursive: true, force: true })));
});

describe("openGrantedLocalAsset", () => {
  it("opens an authorized text attachment through the operating-system boundary", async () => {
    const directory = await mkdtemp(join(tmpdir(), "shiori-open-asset-"));
    temporaryDirectories.push(directory);
    const documentPath = join(directory, "note.md");
    await writeFile(documentPath, "note", "utf-8");
    const registry = new LocalAssetRegistry();
    registry.addTrustedRoot(directory);
    const reference = registry.grantPath(documentPath);
    assert.ok(reference);
    const opened: string[] = [];

    const result = await openGrantedLocalAsset(registry, reference.url, async (path) => {
      opened.push(path);
      return "";
    });

    assert.deepEqual(result, { ok: true, error: null });
    assert.deepEqual(opened, [documentPath]);
  });

  it("does not pass an unauthorized path to the operating system", async () => {
    const registry = new LocalAssetRegistry();
    let called = false;

    const result = await openGrantedLocalAsset(registry, "C:\\private\\secret.txt", async () => {
      called = true;
      return "";
    });

    assert.deepEqual(result, { ok: false, error: "attachment is not authorized" });
    assert.equal(called, false);
  });
});
