import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { matchesPluginUiCode, snapshotPluginUiCode } from "./uiCodeSnapshot";

test("code snapshot covers nested chunks and rejects modified or newly added scripts", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-ui-code-"));
  try {
    await mkdir(join(root, "chunks"));
    const path = join(root, "chunks", "lazy.mjs");
    await writeFile(path, "export const version = 1", "utf8");
    const snapshot = await snapshotPluginUiCode(root);
    const canonical = await realpath(path);
    assert.equal(matchesPluginUiCode(snapshot, canonical, await readFile(path)), true);
    await writeFile(path, "export const version = 2", "utf8");
    assert.equal(matchesPluginUiCode(snapshot, canonical, await readFile(path)), false);
    const added = join(root, "new.mjs");
    await writeFile(added, "export const added = true", "utf8");
    assert.equal(matchesPluginUiCode(snapshot, await realpath(added), await readFile(added)), false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
