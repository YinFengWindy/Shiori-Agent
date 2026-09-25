/// <reference types="node" />

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { it } from "node:test";
import { describeWebpAssetHygiene } from "../testing/webpAssetHygiene";
import { mascotExpressions } from "./mascotExpressions";
import { mascotSprites } from "./mascotSprites";

const here = dirname(fileURLToPath(import.meta.url));
const manifestPath = resolve(here, "mascotSprites.ts");

describeWebpAssetHygiene("mascot sprite hygiene", {
  dir: resolve(here, "../assets/mascot"),
  maxEdge: () => 1920,
  // Cut-outs stand over the scene, so every expression keeps its alpha.
  alphaRequired: () => true,
  manifest: { path: manifestPath, importPattern: /new URL\("\.\.\/assets\/mascot\/([^"]+\.webp)"/g },
});

it("maps every expression to its own sprite file", () => {
  for (const expression of mascotExpressions) {
    const file = fileURLToPath(mascotSprites[expression]);
    assert.equal(basename(file), `yinfeng-${expression}.webp`);
    assert.ok(existsSync(file), file);
  }
});
