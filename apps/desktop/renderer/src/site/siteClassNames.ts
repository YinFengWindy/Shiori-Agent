/**
 * Zero-dependency conditional class name join, local to the site build. The
 * desktop app has its own `cx` in `shared/styles.ts`, but the site
 * deliberately does not depend on desktop business/shared code (see #345 —
 * it only reuses design tokens and Phosphor icons), so this is a small
 * duplicate rather than an import across that boundary.
 */
export function cx(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}
