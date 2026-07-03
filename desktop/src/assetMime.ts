import { extname } from "node:path";

const assetMimeTypes = new Map([
  [".gif", "image/gif"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".md", "text/markdown; charset=utf-8"],
  [".png", "image/png"],
  [".txt", "text/plain; charset=utf-8"],
  [".webp", "image/webp"],
]);

/** Resolves the renderer asset MIME type for a local file path. */
export function getLocalAssetMimeType(assetPath: string): string | undefined {
  return assetMimeTypes.get(extname(assetPath).toLowerCase());
}
