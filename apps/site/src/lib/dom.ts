/*
 * Small DOM helpers shared by the site's page scripts. Fail fast: a page
 * script that cannot find what its markup promised throws, naming it.
 */

/** `value` (an element, an attribute), or an error naming what is missing. */
export function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`${what} is missing`);
  return value;
}
