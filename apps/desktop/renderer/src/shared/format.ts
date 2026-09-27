import { unavailableLocalAssetUrl } from "../../../src/bridge/shared";

/** Converts one trusted bridge path into its renderer-safe opaque URL. */
export type LocalAssetUrlResolver = (path: string) => string;

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

/**
 * Parses a bridge timestamp. Offset-bearing ISO strings keep their instant;
 * naive date-times and bare dates are local wall-clock time (a bare
 * `YYYY-MM-DD` would otherwise parse as UTC midnight). Invalid input is null.
 */
export function parseTimestamp(value?: string): Date | null {
  if (!value) return null;
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Formats bridge timestamps for compact display in chat bubbles. */
export function formatTimestamp(value?: string): string {
  return parseTimestamp(value)?.toLocaleString() ?? "";
}

/** Localized calendar date of a bridge timestamp, for date headings. */
export function formatDate(value?: string): string {
  return parseTimestamp(value)?.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric", weekday: "short" }) ?? "";
}

/** Localized hour and minute of a bridge timestamp. */
export function formatClock(value?: string): string {
  return parseTimestamp(value)?.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) ?? "";
}
