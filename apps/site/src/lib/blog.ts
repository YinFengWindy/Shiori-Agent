import { getCollection, type CollectionEntry } from "astro:content";

/** One post of the blog collection (`content.config.ts`). */
export type BlogPost = CollectionEntry<"blog">;

/** Byline of every post: the posts are written as 吟风. */
export const BLOG_AUTHOR = "吟风";

/** Title of the blog: the list page's heading and the RSS channel's title. */
export const BLOG_TITLE = "博客";

/** What 吟风 says on the list page while no post is published yet (a line of hers, not page copy). */
export const BLOG_EMPTY_LINE = "还在写呢……别催啦，笨蛋。";

/** Description of the blog: the list page's meta description and the RSS channel's. */
export const BLOG_DESCRIPTION = "吟风写的 Shiori 小日记：她会记得什么、怎么慢慢喜欢上你、又为什么会来找你。";

/**
 * Drafts mode: `astro dev --mode drafts` (`pnpm site:dev:drafts`) or
 * `astro build --mode drafts` lists draft posts like published ones, so the
 * owner can read them in place before publishing. Every other run — the
 * production build included — leaves drafts out.
 */
const SHOW_DRAFTS = import.meta.env.MODE === "drafts";

/** The posts to publish, newest first; drafts only in drafts mode. */
export async function getPublishedPosts(): Promise<BlogPost[]> {
  const posts = await getCollection("blog", ({ data }) => SHOW_DRAFTS || !data.draft);
  return posts.sort((a, b) => b.data.date.getTime() - a.data.date.getTime());
}

/** Site path of a post's page. */
export function blogPostPath(post: BlogPost): string {
  return `/blog/${post.id}/`;
}

// Posts carry a day, not a time: read it in UTC, where `YYYY-MM-DD` is parsed.
const postDateFormat = new Intl.DateTimeFormat("zh-CN", { dateStyle: "long", timeZone: "UTC" });

/** A post's day as readers see it, e.g. `2026年10月13日`. */
export function formatPostDate(date: Date): string {
  return postDateFormat.format(date);
}

/** A post's day as `YYYY-MM-DD`, for `<time datetime>` and structured data. */
export function isoPostDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}
