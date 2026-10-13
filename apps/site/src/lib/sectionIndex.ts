/**
 * The section index beside a long reading page (#797): a blog post's table of
 * contents, the changelog's list of versions. Pure, with no DOM, so the
 * entries and the current-section rule are unit-testable.
 */

/** One link of an index: a section's anchor and what it is called. */
export interface SectionIndexEntry {
  /** The `id` of the section's element on the page (its anchor). */
  id: string;
  label: string;
  /** Nesting: 0 for a top-level section (a post's h2, a version), 1 for one inside it (a post's h3). */
  level: 0 | 1;
  /** A line under the label (a version's day). */
  note?: string;
}

/** A heading as Astro's `render()` reports it for an MDX entry. */
export interface RenderedHeading {
  depth: number;
  slug: string;
  text: string;
}

/**
 * A post's table of contents from its rendered headings: its h2s, each with
 * the h3s under it as sub-entries; deeper headings stay out. Empty when the
 * post has fewer than two h2s, where a table of contents would only repeat
 * the one heading.
 */
export function postTableOfContents(headings: readonly RenderedHeading[]): SectionIndexEntry[] {
  const entries: SectionIndexEntry[] = [];
  for (const heading of headings) {
    if (!heading.slug) throw new Error(`heading "${heading.text}" has no id to link to`);
    if (heading.depth === 2) entries.push({ id: heading.slug, label: heading.text, level: 0 });
    // An h3 before the first h2 has no section to sit in.
    else if (heading.depth === 3 && entries.length > 0) entries.push({ id: heading.slug, label: heading.text, level: 1 });
  }
  return entries.filter((entry) => entry.level === 0).length >= 2 ? entries : [];
}

/** Where the page is, as far as the current section goes. */
export interface SectionPosition {
  /** Each indexed section's top edge relative to the viewport top, in page order (px). */
  tops: readonly number[];
  /** The reading line: a section whose top has risen to it is being read (just under the sticky top bar). */
  line: number;
  /** The page is scrolled to its end (it cannot go further down). */
  atEnd: boolean;
  /** The viewport height (px). */
  viewportHeight: number;
}

/**
 * The index of the section being read, or -1 before the first one (a post's
 * opening lines). It is the last section whose top has reached the reading
 * line. At the end of the page the last sections may never rise that far, so
 * there the last section whose top is on screen counts instead: following a
 * link to the last section always marks it.
 */
export function currentSectionIndex({ tops, line, atEnd, viewportHeight }: SectionPosition): number {
  if (!Number.isFinite(line)) throw new Error(`line must be finite, got ${line}`);
  let current = -1;
  for (const [index, top] of tops.entries()) {
    if (top <= line + 1) current = index;
  }
  if (atEnd) {
    for (const [index, top] of tops.entries()) {
      if (index > current && top < viewportHeight) current = index;
    }
  }
  return current;
}
