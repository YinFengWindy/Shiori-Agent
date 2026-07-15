import { unavailableLocalAssetUrl } from "../../../src/shared";

type LocalAssetUrlResolver = (path: string) => string;

function resolveDesktopLocalAssetUrl(path: string): string {
  if (typeof window === "undefined") {
    return unavailableLocalAssetUrl;
  }
  return window.miraDesktop.localAssetUrl(path);
}

/** Resolves a local path to an opaque renderer-safe asset URL through the desktop bridge. */
export function toFileUrl(
  path: string,
  resolveLocalAssetUrl: LocalAssetUrlResolver = resolveDesktopLocalAssetUrl,
): string {
  return resolveLocalAssetUrl(path);
}

/** Formats bridge timestamps for compact display in chat bubbles. */
export function formatTimestamp(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}
