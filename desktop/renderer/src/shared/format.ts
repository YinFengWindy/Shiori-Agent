/** Converts an absolute Windows or POSIX path into a renderer-safe file URL. */
export function toFileUrl(path: string): string {
  return `file:///${path.replace(/\\/g, "/").replace(/"/g, "%22")}`;
}

/** Formats bridge timestamps for compact display in chat bubbles. */
export function formatTimestamp(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}
