/// <reference types="node" />

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describeWebpAssetHygiene } from "../testing/webpAssetHygiene";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * Full-viewport backgrounds get a larger budget than other art: they are
 * cover-fitted to the whole window, so at 1920px they visibly soften on
 * 2560-wide / HiDPI screens next to the crisp cut-out sprites (#360). The
 * owner's picks are 2x-upscaled to 2432px; 2560 is the cap for any refresh.
 */
describeWebpAssetHygiene("scene background hygiene", {
  dir: resolve(here, "../assets/scene"),
  maxEdge: () => 2560,
  alphaRequired: () => false,
  manifest: { path: resolve(here, "sceneBackgrounds.ts"), importPattern: /new URL\("\.\.\/assets\/scene\/([^"]+\.webp)"/g },
});
