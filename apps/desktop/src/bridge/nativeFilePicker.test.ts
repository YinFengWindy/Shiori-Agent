import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { test } from "node:test";
import type { OpenDialogOptions } from "electron";
import { pickNativeDirectory, pickNativeFilePaths, pickNativeFiles } from "./nativeFilePicker";

const options = { namespace: "sample-package", multiple: false, maxFileBytes: 64,
  filters: [{ name: "Package files", extensions: ["zip"] }] };

test("uses plugin-supplied native filters and returns only copied dialog selections", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-picker-dialog-"));
  try {
    const source = join(root, "selected.zip"); await writeFile(source, "selected bytes", "utf8");
    const dialogs: OpenDialogOptions[] = [];
    const staged = await pickNativeFiles(options, join(root, "imports"), async (value) => {
      dialogs.push(value); return { canceled: false, filePaths: [source] };
    });
    assert.deepEqual(dialogs, [{ properties: ["openFile"], filters: options.filters }]);
    assert.notEqual(staged[0], source);
    assert.equal(await readFile(staged[0], "utf8"), "selected bytes");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("native cancellation discards even supplied result paths and multiple selection is explicit", async () => {
  const dialogs: OpenDialogOptions[] = [];
  const result = await pickNativeFiles({ ...options, multiple: true }, "unused-imports", async (value) => {
    dialogs.push(value); return { canceled: true, filePaths: ["/must-not-be-read.zip"] };
  });
  assert.deepEqual(result, []);
  assert.deepEqual(dialogs[0].properties, ["openFile", "multiSelections"]);
  let opened = false;
  await assert.rejects(pickNativeFiles({ ...options, source: "/arbitrary/path.zip" }, "unused-imports", async () => {
    opened = true; return { canceled: false, filePaths: [] };
  }), /不支持/);
  assert.equal(opened, false);
});

test("original-path picks return the selected path itself and write nothing beside the imports root", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-picker-paths-"));
  try {
    const source = join(root, "selected.zip"); await writeFile(source, "selected bytes", "utf8");
    const pathOptions = { multiple: false, maxFileBytes: 64, filters: options.filters };
    const dialogs: OpenDialogOptions[] = [];
    const picked = await pickNativeFilePaths(pathOptions, async (value) => {
      dialogs.push(value); return { canceled: false, filePaths: [source] };
    });
    assert.deepEqual(picked, [source]);
    assert.deepEqual(dialogs, [{ properties: ["openFile"], filters: options.filters }]);
    assert.deepEqual(await readdir(root), ["selected.zip"]);
    assert.deepEqual(await pickNativeFilePaths(pathOptions, async () => ({ canceled: true, filePaths: [source] })), []);
    await assert.rejects(pickNativeFilePaths(options, async () => ({ canceled: false, filePaths: [source] })), /不支持/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("directory picks may create a directory and answer null on cancellation", async () => {
  const dialogs: OpenDialogOptions[] = [];
  const directory = join(tmpdir(), "chosen-runtime");
  assert.equal(await pickNativeDirectory(async (value) => { dialogs.push(value); return { canceled: false, filePaths: [directory] }; }), directory);
  assert.deepEqual(dialogs, [{ properties: ["openDirectory", "createDirectory"] }]);
  assert.equal(await pickNativeDirectory(async () => ({ canceled: true, filePaths: [directory] })), null);
  assert.equal(await pickNativeDirectory(async () => ({ canceled: false, filePaths: [] })), null);
});
