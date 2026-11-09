import assert from "node:assert/strict";
import { test } from "node:test";
import { petModelKey } from "@yinfengwindy/shiori-pet";
import { readPetPackages } from "./petPackages";

const sprite = { plugin_id: "pet_codex_sprite", service_id: "models" };
const other = { plugin_id: "other", service_id: "models" };

test("identical model ids remain separate selections across appearance providers", () => {
  const parsed = readPetPackages({
    selected_model: { provider: other, model_id: "cat" }, providers: [],
    packages: [
      { id: "cat", provider: sprite, display_name: "精灵猫", preview_abs: "C:/private/cat.png" },
      { id: "cat", provider: other, display_name: "另一只猫", preview_abs: null },
    ],
  }, () => "shiori-asset://local/opaque");
  assert.ok(parsed.selectedModel);
  assert.notEqual(petModelKey(parsed.packages[0].reference), petModelKey(parsed.selectedModel));
  assert.equal(petModelKey(parsed.packages[1].reference), petModelKey(parsed.selectedModel));
  assert.doesNotMatch(JSON.stringify(parsed), /C:\/private/);
});

test("an unavailable provider does not erase the saved model reference", () => {
  const selected_model = { provider: sprite, model_id: "cat" };
  const parsed = readPetPackages({ selected_model, providers: [], packages: [] }, () => "");
  assert.deepEqual(parsed.selectedModel, selected_model);
});

test("malformed provider identity and import policy fail instead of selecting a guessed owner", () => {
  assert.throws(() => readPetPackages({ selected_model: null, providers: [], packages: [
    { id: "cat", display_name: "没有提供者" },
  ] }, () => ""), /提供者/);
  assert.throws(() => readPetPackages({ selected_model: null, packages: [], providers: [
    { ...sprite, label: "精灵图", import: { namespace: "pets", max_file_bytes: -1, label: "ZIP", extensions: ["zip"] } },
  ] }, () => ""), /导入配置/);
});
