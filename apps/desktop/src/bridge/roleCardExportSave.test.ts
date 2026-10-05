import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir, rm, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it } from "node:test";
import type { SaveDialogOptions } from "electron";
import { saveRoleCardExport } from "./roleCardExportSave";

const exportId = "a".repeat(32);
const data = Buffer.from("immutable snapshot");
const bridge: Parameters<typeof saveRoleCardExport>[1] = {
  invoke: async () => ({ id: "read", method: "roles.cardExport.read", type: "response", error: null,
    payload: { name: "小诗:/角色", format: "charx", data_base64: data.toString("base64") } }),
};

it("uses role name and matching format, and saves exactly the preview snapshot", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-export-"));
  try {
    const destination = join(root, "chosen.charx");
    const dialogs: SaveDialogOptions[] = [];
    assert.deepEqual(await saveRoleCardExport(exportId, bridge, async (options) => {
      dialogs.push(options); return { canceled: false, filePath: destination };
    }), { saved: true });
    assert.equal(dialogs[0].defaultPath, "小诗__角色.charx");
    assert.deepEqual(dialogs[0].filters, [{ name: "CHARX 角色卡", extensions: ["charx"] }]);
    assert.deepEqual(await readFile(destination), data);
    assert.deepEqual(await readdir(root), ["chosen.charx"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

it("does not write or report success when the native picker cancels", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-export-cancel-"));
  try {
    assert.deepEqual(await saveRoleCardExport(exportId, bridge, async () => ({ canceled: true, filePath: join(root, "ignored.charx") })), { saved: false });
    assert.deepEqual(await readdir(root), []);
  } finally { await rm(root, { recursive: true, force: true }); }
});

it("keeps an existing file when appending a format extension would change the confirmed target", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-export-extension-"));
  try {
    const destination = join(root, "existing.charx");
    await writeFile(destination, "keep me", "utf8");
    await assert.rejects(saveRoleCardExport(exportId, bridge, async () => ({ canceled: false, filePath: join(root, "existing") })), /exist|EEXIST/i);
    assert.equal(await readFile(destination, "utf8"), "keep me");
    assert.deepEqual(await readdir(root), ["existing.charx"]);
    await saveRoleCardExport(exportId, bridge, async () => ({ canceled: false, filePath: destination }));
    assert.deepEqual(await readFile(destination), data);
  } finally { await rm(root, { recursive: true, force: true }); }
});

it("propagates filesystem failure, cleans temporary files, and permits retry", async () => {
  const root = await mkdtemp(join(tmpdir(), "shiori-export-failure-"));
  try {
    const directory = join(root, "directory.charx");
    await mkdir(directory);
    await assert.rejects(saveRoleCardExport(exportId, bridge, async () => ({ canceled: false, filePath: directory })));
    assert.deepEqual(await readdir(root), ["directory.charx"]);
    assert.deepEqual(await saveRoleCardExport(exportId, bridge, async () => ({ canceled: false, filePath: join(root, "retry") })), { saved: true });
    assert.deepEqual(await readFile(join(root, "retry.charx")), data);
  } finally { await rm(root, { recursive: true, force: true }); }
});

it("rejects renderer paths and expired snapshots before showing the save dialog", async () => {
  let dialogs = 0;
  const picker = async () => { dialogs += 1; return { canceled: true, filePath: "" }; };
  await assert.rejects(saveRoleCardExport("C:/private/file", bridge, picker), /无效/);
  await assert.rejects(saveRoleCardExport(exportId, { invoke: async () => ({ id: "read", type: "response", method: "roles.cardExport.read", payload: {}, error: { code: "invalid", message: "预览失效" } }) }, picker), /失效/);
  assert.equal(dialogs, 0);
});
