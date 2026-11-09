import assert from "node:assert/strict";
import { test } from "node:test";
import { pickPetPackageFile } from "./petPackagePicker";

const policy = { namespace: "pet_codex_sprite-pets", multiple: false,
  filters: [{ name: "Codex Pet Package", extensions: ["zip"] }], maxFileBytes: 32 * 1024 * 1024 };

test("provider staging policy is passed intact and cancel/failure never yield an import path", async () => {
  const source = await pickPetPackageFile(async (options) => {
    assert.deepEqual(options, { namespace: "pet_codex_sprite-pets", multiple: false,
      filters: [{ name: "Codex Pet Package", extensions: ["zip"] }], maxFileBytes: 32 * 1024 * 1024 });
    return ["/private/imports/package.zip"];
  }, policy);
  assert.equal(source, "/private/imports/package.zip");
  assert.equal(await pickPetPackageFile(async () => [], policy), null);
  await assert.rejects(pickPetPackageFile(async () => { throw new Error("native dialog failed"); }, policy), /native dialog failed/);
});
