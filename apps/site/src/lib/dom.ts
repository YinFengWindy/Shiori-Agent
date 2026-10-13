/*
 * A small fail-fast helper shared by the site's page scripts and pages: what
 * the markup or the content promised is there, or an error names it.
 */

/** `value` (an element, an attribute, a looked-up entry), or an error naming what is missing. */
export function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`${what} is missing`);
  return value;
}
