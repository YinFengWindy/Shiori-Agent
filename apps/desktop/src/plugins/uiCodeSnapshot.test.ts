import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { matchesPluginUiCode, snapshotPluginUiCode } from "./uiCodeSnapshot";

test("code snapshot covers nested chunks and rejects modified or newly added scripts", async () => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "shiori-ui-code-")));
  try {
    await mkdir(join(root, "chunks"));
    const path = join(root, "chunks", "lazy.mjs");
    await writeFile(path, "export const version = 1", "utf8");
    const approved = { "chunks/lazy.mjs": createHash("sha256").update(await readFile(path)).digest("hex") };
    const snapshot = await snapshotPluginUiCode(root, approved);
    const canonical = await realpath(path);
    assert.equal(matchesPluginUiCode(snapshot, canonical, await readFile(path)), true);
    await writeFile(path, "export const version = 2", "utf8");
    assert.equal(matchesPluginUiCode(snapshot, canonical, await readFile(path)), false);
    await assert.rejects(snapshotPluginUiCode(root, approved), /changed after approval/);
    const added = join(root, "new.mjs");
    await writeFile(added, "export const added = true", "utf8");
    assert.equal(matchesPluginUiCode(snapshot, await realpath(added), await readFile(added)), false);
  } finally { await rm(root, { recursive: true, force: true }); }
});
