import assert from "node:assert/strict";
import crypto from "node:crypto";
import { syncBuiltinESMExports } from "node:module";
import { mkdtemp, mkdir, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { basename, dirname, join, relative } from "node:path";
import { tmpdir } from "node:os";
import { afterEach, test } from "node:test";
import { stagePickedFiles } from "./pickedFileStaging";
import { resolveLocalAssetCandidate } from "./localAssetPolicy";
import { importLocalAssets } from "./localAssetImport";
import type { NativeFilePickerOptions } from "./filePickerContract";

const temporary: string[] = [];
const policy: NativeFilePickerOptions = { namespace: "sample-packages", maxFileBytes: 64, filters: [{ name: "Packages", extensions: ["zip"] }] };
afterEach(async () => { await Promise.all(temporary.splice(0).map((path) => rm(path, { recursive: true, force: true }))); });
async function fixture() {
  const root = await realpath(await mkdtemp(join(tmpdir(), "shiori-picker-"))); temporary.push(root);
  const source = join(root, "package.ZIP");
  await writeFile(source, Buffer.from([0x50, 0x4b, 3, 4]));
  return { root, source, imports: join(root, "imports") };
}

test("stages selected package bytes privately and never turns ZIP into a local media asset", async () => {
  const { source, imports } = await fixture();
  const [staged] = await stagePickedFiles([source], imports, policy);
  assert.notEqual(staged, source);
  assert.match(basename(staged), /-package\.ZIP$/);
  assert.ok(!relative(imports, staged).startsWith(".."));
  assert.deepEqual(await readFile(staged), await readFile(source));
  assert.equal(resolveLocalAssetCandidate(staged), null);
  await assert.rejects(importLocalAssets([staged], imports), /unsupported local asset/);
});

test("rejects oversize files, directories, unexpected extensions and traversal without leaving partial batches", async () => {
  const { root, source, imports } = await fixture();
  await assert.rejects(stagePickedFiles([source], imports, { ...policy, maxFileBytes: 3 }), /大小限制/);
  assert.deepEqual(await readdir(join(imports, policy.namespace)), []);
  const directory = join(root, "folder.zip"); await mkdir(directory);
  await assert.rejects(stagePickedFiles([directory], imports, policy), /不是普通文件/);
  const wrong = join(root, "wrong.txt"); await writeFile(wrong, "private", "utf8");
  await assert.rejects(stagePickedFiles([source, wrong], imports, { ...policy, multiple: true }), /类型不受支持/);
  assert.deepEqual(await readdir(join(imports, policy.namespace)), []);
  await assert.rejects(stagePickedFiles([source], imports, { ...policy, namespace: "../escape" }), /命名空间无效/);
  await assert.rejects(stagePickedFiles([source, source], imports, policy), /数量超过限制/);
});

test("refuses a namespace redirected outside the trusted imports root", async () => {
  const { root, source, imports } = await fixture();
  const outside = join(root, "outside"); await mkdir(outside); await mkdir(imports);
  await symlink(outside, join(imports, policy.namespace), process.platform === "win32" ? "junction" : "dir");
  await assert.rejects(stagePickedFiles([source], imports, policy), /目录越界/);
  assert.deepEqual(await readdir(outside), []);
});

test("keeps caller-owned filenames and extensions for non-media role card staging", async () => {
  const { root, imports } = await fixture();
  const source = join(root, "character.json"); await writeFile(source, '{"name":"Mira"}', "utf8");
  const [staged] = await stagePickedFiles([source], imports, { namespace: "role-cards", maxFileBytes: 64,
    filters: [{ name: "Role cards", extensions: ["json"] }] });
  assert.match(basename(staged), /-character\.json$/);
  assert.equal(basename(dirname(staged)), "role-cards");
  assert.equal(await readFile(staged, "utf8"), '{"name":"Mira"}');
});


test("rollback leaves a pre-existing destination untouched when exclusive creation fails", async (context) => {
  const { source, imports } = await fixture();
  const namespace = join(imports, policy.namespace); await mkdir(namespace, { recursive: true });
  const fixed = "00000000-0000-4000-8000-000000000000";
  const existing = join(namespace, `${fixed}-${basename(source)}`);
  await writeFile(existing, "keep existing", "utf8");
  const mocked = context.mock.method(crypto, "randomUUID", () => fixed);
  syncBuiltinESMExports();
  try {
    await assert.rejects(stagePickedFiles([source], imports, policy), /EEXIST/);
    assert.equal(await readFile(existing, "utf8"), "keep existing");
  } finally { mocked.mock.restore(); syncBuiltinESMExports(); }
});
