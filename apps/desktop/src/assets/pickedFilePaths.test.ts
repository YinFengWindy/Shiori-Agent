import assert from "node:assert/strict";
import { mkdir, mkdtemp, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import { admitPickedFilePaths } from "./pickedFilePaths";

const policy = { maxFileBytes: 4, filters: [{ name: "Archives", extensions: ["7z"] }] };

test("admits original paths under the staging policy without reading or copying them", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-picked-paths-"));
  try {
    const source = join(root, "Runtime.7Z"); await writeFile(source, "1234", "utf8");
    assert.deepEqual(await admitPickedFilePaths([source], policy), [source]);
    await writeFile(join(root, "large.7z"), "12345", "utf8");
    await assert.rejects(admitPickedFilePaths([join(root, "large.7z")], policy), /大小限制/);
    await mkdir(join(root, "folder.7z"));
    await assert.rejects(admitPickedFilePaths([join(root, "folder.7z")], policy), /不是普通文件/);
    await writeFile(join(root, "notes.txt"), "1", "utf8");
    await assert.rejects(admitPickedFilePaths([join(root, "notes.txt")], policy), /类型不受支持/);
    await assert.rejects(admitPickedFilePaths([source, source], policy), /数量超过限制/);
    const stagingOptions = { ...policy, namespace: "packs" };
    await assert.rejects(admitPickedFilePaths([source], stagingOptions), /不支持/);
    assert.deepEqual((await readdir(root)).sort(), ["Runtime.7Z", "folder.7z", "large.7z", "notes.txt"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});
