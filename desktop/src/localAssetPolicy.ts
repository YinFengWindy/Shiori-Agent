import { realpathSync, statSync } from "node:fs";
import { isAbsolute, normalize, relative } from "node:path";
import { getLocalAssetMimeType } from "./assetMime.js";

export type LocalAssetKind = "image" | "document";

export type LocalAssetCandidate = {
  requestedPath: string;
  canonicalPath: string;
  kind: LocalAssetKind;
  mimeType: string;
};

const trustedSinglePathFields = new Set([
  "avatar_abs",
  "base_image_path",
  "chat_background_abs",
  "image_path",
]);

const trustedPathListFields = new Set([
  "illustrations_abs",
  "media",
  "output_paths",
  "role_asset_paths",
]);

export function localAssetPathKey(path: string): string {
  const normalizedPath = normalize(path);
  return process.platform === "win32" ? normalizedPath.toLocaleLowerCase("en-US") : normalizedPath;
}

/** Resolves a supported ordinary file to its canonical local asset identity. */
export function resolveLocalAssetCandidate(path: string): LocalAssetCandidate | null {
  const requestedPath = path.trim();
  if (!requestedPath || !isAbsolute(requestedPath)) {
    return null;
  }
  const mimeType = getLocalAssetMimeType(requestedPath);
  const kind = mimeType?.startsWith("image/")
    ? "image"
    : mimeType?.startsWith("text/")
      ? "document"
      : null;
  if (!mimeType || !kind) {
    return null;
  }
  try {
    const canonicalPath = realpathSync(requestedPath);
    if (!statSync(canonicalPath).isFile()) {
      return null;
    }
    return { requestedPath, canonicalPath, kind, mimeType };
  } catch {
    return null;
  }
}

/** Checks canonical containment without accepting sibling-prefix or cross-drive paths. */
export function isLocalAssetInsideRoot(canonicalPath: string, root: string): boolean {
  try {
    const canonicalRoot = realpathSync(root);
    const relativePath = relative(canonicalRoot, canonicalPath);
    const parentPrefix = `..${process.platform === "win32" ? "\\" : "/"}`;
    return relativePath !== ""
      && relativePath !== ".."
      && !relativePath.startsWith(parentPrefix)
      && !isAbsolute(relativePath);
  } catch {
    return false;
  }
}

/** Collects only explicitly declared asset fields from a trusted bridge payload. */
export function collectTrustedLocalAssetPaths(payload: unknown): string[] {
  const paths: string[] = [];
  function visit(value: unknown, fieldName = ""): void {
    if (typeof value === "string") {
      if (trustedSinglePathFields.has(fieldName) || trustedPathListFields.has(fieldName)) {
        paths.push(value);
      }
      return;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        visit(item, fieldName);
      }
      return;
    }
    if (value && typeof value === "object") {
      for (const [key, item] of Object.entries(value)) {
        visit(item, key);
      }
    }
  }
  visit(payload);
  return paths;
}
