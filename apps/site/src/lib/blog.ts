import { getCollection, type CollectionEntry } from "astro:content";
import { DEFAULT_LOCALE, LOCALES, LOCALE_INFO, type Locale, type PageVersions, localePath } from "../i18n/locales";

/*
 * The blog in each language (#773, #807): the Chinese posts
 * (`src/content/blog`) and their English versions (`src/content/blog-en`,
 * same slug; content.config.ts). The words around the posts (title,
 * description, byline) are in the dictionaries' `blog`.
 */

/** Each language's collection of posts. */
const COLLECTIONS = { zh: "blog", en: "blogEn" } as const satisfies Record<Locale, string>;

/** One post, in any language. */
export type BlogPost = CollectionEntry<(typeof COLLECTIONS)[Locale]>;

/**
 * Drafts mode: `astro dev --mode drafts` (`pnpm site:dev:drafts`) or
 * `astro build --mode drafts` lists draft posts like published ones, so the
 * owner can read them in place before publishing. Every other run — the
 * production build included — leaves drafts out.
 */
const SHOW_DRAFTS = import.meta.env.MODE === "drafts";

/**
 * The posts to publish in `locale`, newest first; drafts only in drafts
 * mode. Posts carry a day, so same-day posts fall back to their id to keep
 * one stable order.
 */
export async function getPublishedPosts(locale: Locale): Promise<BlogPost[]> {
  const posts: BlogPost[] = await getCollection(COLLECTIONS[locale], ({ data }) => SHOW_DRAFTS || !data.draft);
  return posts.sort((a, b) => b.data.date.getTime() - a.data.date.getTime() || a.id.localeCompare(b.id));
}

/** Site path of the post `slug` in `locale`: `/blog/<slug>/`, `/en/blog/<slug>/`. */
export function blogPostPath(slug: string, locale: Locale): string {
  return localePath(locale, `/blog/${slug}/`);
}

/**
 * Every published post's versions, by slug: the post in each language it is
 * published in (`PageVersions`), for its hreflang alternates and language
 * switch. A translation must translate a published Chinese post: one
 * without fails the build, as its slug would pair with nothing.
 */
export async function postVersionsBySlug(): Promise<ReadonlyMap<string, PageVersions>> {
  const versions = new Map<string, Partial<Record<Locale, string>>>();
  for (const post of await getPublishedPosts(DEFAULT_LOCALE)) versions.set(post.id, { [DEFAULT_LOCALE]: blogPostPath(post.id, DEFAULT_LOCALE) });
  for (const locale of LOCALES) {
    if (locale === DEFAULT_LOCALE) continue;
    for (const post of await getPublishedPosts(locale)) {
      const entry = versions.get(post.id);
      if (!entry) throw new Error(`the ${locale} post ${post.id} translates no published ${DEFAULT_LOCALE} post of that slug`);
      entry[locale] = blogPostPath(post.id, locale);
    }
  }
  return versions;
}

/** A post's day as readers of `locale` see it, e.g. `2026年10月13日`, `October 13, 2026`. */
export function formatPostDate(date: Date, locale: Locale): string {
  // Posts carry a day, not a time: read it in UTC, where `YYYY-MM-DD` is parsed.
  return new Intl.DateTimeFormat(LOCALE_INFO[locale].htmlLang, { dateStyle: "long", timeZone: "UTC" }).format(date);
}

/** A post's day as `YYYY-MM-DD`, for `<time datetime>` and structured data. */
export function isoPostDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** What a post page is built from: the post, and its versions (`postVersionsBySlug`). */
export interface PostPageProps {
  post: BlogPost;
  versions: PageVersions;
}

/**
 * The post pages of `locale` (`getStaticPaths` of pages/blog/[slug].astro
 * and pages/en/blog/[slug].astro): one per post published in it, by slug,
 * each with its versions.
 */
export async function postStaticPaths(locale: Locale) {
  const versionsBySlug = await postVersionsBySlug();
  const posts = await getPublishedPosts(locale);
  return posts.map((post) => {
    const versions = versionsBySlug.get(post.id);
    if (!versions) throw new Error(`post ${post.id} has no versions: it is not published in ${DEFAULT_LOCALE}`);
    const props: PostPageProps = { post, versions };
    return { params: { slug: post.id }, props };
  });
}
