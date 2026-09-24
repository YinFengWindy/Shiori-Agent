/// <reference types="node" />

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { it } from "node:test";
import { describeWebpAssetHygiene } from "../testing/webpAssetHygiene";
import { mascotExpressions } from "./mascotExpressions";

const here = dirname(fileURLToPath(import.meta.url));
const manifestPath = resolve(here, "mascotSprites.ts");

describeWebpAssetHygiene("mascot sprite hygiene", {
  dir: resolve(here, "../assets/mascot"),
  maxEdge: () => 1920,
  // Cut-outs stand over the scene, so every expression keeps its alpha.
  alphaRequired: () => true,
  manifest: { path: manifestPath, importPattern: /from "\.\.\/assets\/mascot\/([^"]+\.webp)"/g },
});

it("maps every expression to its own sprite file", () => {
  const source = readFileSync(manifestPath, "utf8");
  for (const expression of mascotExpressions) {
    assert.ok(source.includes(`import ${expression} from "../assets/mascot/yinfeng-${expression}.webp"`), expression);
  }
});
