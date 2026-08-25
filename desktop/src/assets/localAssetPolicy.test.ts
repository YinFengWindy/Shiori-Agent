import assert from "node:assert/strict";
import test from "node:test";

import { collectTrustedLocalAssetPaths } from "./localAssetPolicy.js";

test("pet package renderer assets are collected from trusted bridge payloads", () => {
  const previewPath = "C:\\workspace\\roles\\assets\\role-1\\pets\\pet-1\\preview.png";
  const spritesheetPath = "C:\\workspace\\roles\\assets\\role-1\\pets\\pet-1\\spritesheet.webp";

  const paths = collectTrustedLocalAssetPaths({
    pet_packages: [{
      preview_abs: previewPath,
      spritesheet_abs: spritesheetPath,
    }],
  });

  assert.deepEqual(paths, [previewPath, spritesheetPath]);
});
