import type { ExternalLinkOpenResult } from "./bridge/shared.js";

/** Accepts only user-visible external protocols supported by the desktop shell. */
export function normalizeExternalLink(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.protocol === "http:" || url.protocol === "https:") {
    return url.origin === "null" || !url.hostname ? null : url.toString();
  }
  if (url.protocol === "mailto:" && url.pathname.trim()) {
    return url.toString();
  }
  return null;
}

/** Opens a validated external link through the injected operating-system boundary. */
export async function openExternalLink(
  value: string,
  openExternal: (url: string) => Promise<void>,
): Promise<ExternalLinkOpenResult> {
  const url = normalizeExternalLink(value);
  if (!url) return { ok: false, error: "external link protocol is not authorized" };
  await openExternal(url);
  return { ok: true, error: null };
}
