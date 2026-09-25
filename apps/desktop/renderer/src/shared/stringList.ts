/** Appends one list-editor entry; blank or duplicate entries leave the list unchanged. */
export function appendStringListItem(items: readonly string[], raw: string): string[] {
  const value = raw.trim();
  if (!value || items.includes(value)) return [...items];
  return [...items, value];
}
