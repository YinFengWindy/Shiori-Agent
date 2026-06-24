/** Converts an absolute Windows or POSIX path into a renderer-safe file URL. */
export function toFileUrl(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const encodedSegments = normalized.split("/").map((segment, index) => {
    if (index === 0 && /^[A-Za-z]:$/.test(segment)) {
      return segment;
    }
    return encodeURIComponent(segment);
  });

  if (/^[A-Za-z]:/.test(normalized)) {
    return `file:///${encodedSegments.join("/")}`;
  }

  if (normalized.startsWith("//")) {
    return `file://${encodedSegments.slice(2).join("/")}`;
  }

  return `file://${encodedSegments.join("/")}`;
}

/** Formats bridge timestamps for compact display in chat bubbles. */
export function formatTimestamp(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}
