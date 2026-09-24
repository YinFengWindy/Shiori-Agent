/// <reference types="node" />

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describeWebpAssetHygiene } from "../../shared/testing/webpAssetHygiene";

const here = dirname(fileURLToPath(import.meta.url));

// Deliberately not colocated inside site/assets/: `pnpm run build:site`
// scans that whole directory for the actual image imports, so a stray
// non-image file there would confuse that (unrelated) static analysis.
// The scene backgrounds moved to shared/assets/scene (see sceneBackgrounds.test.ts).
describeWebpAssetHygiene("site asset hygiene", {
  dir: resolve(here, "../assets"),
  maxEdge: () => 1920,
  // Cut-out standing sprites must keep their transparent background.
  alphaRequired: (file) => /^sprite-\d+\.webp$/.test(file),
  manifest: { path: resolve(here, "siteAssets.ts"), importPattern: /from "\.\.\/assets\/([^"]+\.webp)"/g },
});
