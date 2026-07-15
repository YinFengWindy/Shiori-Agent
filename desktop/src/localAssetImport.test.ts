/// <reference types="node" />

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { afterEach, describe, it } from "node:test";
import { importLocalAssets } from "./localAssetImport";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((path) => (
    rm(path, { recursive: true, force: true })
  )));
});

async function createTemporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(join(tmpdir(), "shiori-local-import-"));
  temporaryDirectories.push(directory);
  return directory;
}

describe("importLocalAssets", () => {
  it("copies a picker file to its private content-addressed path", async () => {
    const directory = await createTemporaryDirectory();
    const sourcePath = join(directory, "outside.PNG");
    const importsRoot = join(directory, "private_runtime", "imports");
    const data = Buffer.from("image-content");
    await writeFile(sourcePath, data);

    const [importedPath] = await importLocalAssets([sourcePath], importsRoot);

    const digest = createHash("sha256").update(data).digest("hex");
    assert.equal(dirname(importedPath), join(importsRoot, digest));
    assert.equal(basename(importedPath), "outside.PNG");
    assert.deepEqual(await readFile(importedPath), data);
    assert.notEqual(importedPath, sourcePath);
  });

  it("deduplicates repeated selections while preserving the display filename", async () => {
    const directory = await createTemporaryDirectory();
    const firstPath = join(directory, "first.txt");
    const importsRoot = join(directory, "imports");
    await writeFile(firstPath, "same", "utf-8");

    const imported = await importLocalAssets([firstPath, firstPath], importsRoot);

    assert.equal(imported[0], imported[1]);
    assert.equal(basename(imported[0]), "first.txt");
  });

  it("rejects unsupported files instead of copying or authorizing them", async () => {
    const directory = await createTemporaryDirectory();
    const sourcePath = join(directory, "secret.json");
    await writeFile(sourcePath, "{}", "utf-8");

    await assert.rejects(
      importLocalAssets([sourcePath], join(directory, "imports")),
      /unsupported local asset/,
    );
  });
});
