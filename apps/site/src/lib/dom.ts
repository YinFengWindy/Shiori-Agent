/*
 * A small fail-fast helper shared by the site's page scripts: what the
 * markup promised is on the page, or an error names what is missing.
 */

/** `value` (an element, an attribute), or an error naming what is missing. */
export function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`${what} is missing`);
  return value;
}
