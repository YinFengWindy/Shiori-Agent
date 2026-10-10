import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describeWebpAssetHygiene } from "../../desktop/renderer/src/shared/testing/webpAssetHygiene";

const here = dirname(fileURLToPath(import.meta.url));

// The site's own art (the scene backgrounds are the desktop's files and are
// covered by its sceneBackgrounds.test.ts). Same rules the art had under the
// old desktop-hosted site: real WebP, <= 1920px, no metadata, alpha sprites.
describeWebpAssetHygiene("site art hygiene", {
  dir: resolve(here, "../src/assets/art"),
  maxEdge: () => 1920,
  // Cut-out standing sprites must keep their transparent background.
  alphaRequired: (file) => /^sprite-\d+\.webp$/.test(file),
  manifest: { path: resolve(here, "../src/lib/siteAssets.ts"), importPattern: /from "\.\.\/assets\/art\/([^"]+\.webp)"/g },
});
