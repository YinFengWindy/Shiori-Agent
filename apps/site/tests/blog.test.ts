import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  type BuiltSite,
  ORIGIN,
  dist,
  draftsDist,
  sitemapPages,
} from "./support/builtSite";

/*
 * The blog (#773) as built. The production build (dist/) must leave draft
 * posts out of every page, the feed and the sitemap. The posts' own pages
 * are checked in the drafts-mode build (dist-drafts/), which renders every
 * post, drafts included: that proves what a published post's page carries
 * without publishing a test post on the live site.
 */

const blogDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "content", "blog");

interface SourcePost {
  readonly slug: string;
  readonly title: string;
  readonly description: string;
  readonly date: string;
  readonly draft: boolean;
  /** Whether it has a cover picture. */
  readonly cover: boolean;
  /** The post's first paragraph, as written. */
  readonly opening: string;
  /** How many `##` sections it has. */
  readonly sections: number;
}

/** The posts as written in src/content/blog, read straight from their frontmatter. */
const sourcePosts: SourcePost[] = readdirSync(blogDir)
  .filter((file) => file.endsWith(".mdx"))
  .map((file) => {
    const text = readFileSync(resolve(blogDir, file), "utf8").replaceAll("\r\n", "\n");
    const [, frontmatter = "", body = ""] = text.match(/^---\n(.*?)\n---\n(.*)$/s) ?? [];
    const field = (key: string) => {
      const value = frontmatter.match(new RegExp(`^${key}: (.+)$`, "m"))?.[1];
      assert.ok(value, `${file} has no ${key}`);
      return value;
    };
    const opening = body.split("\n").find((line) => line.trim() !== "" && !line.startsWith("#"));
    assert.ok(opening, `${file} has no text`);
    return {
      slug: file.replace(/\.mdx$/, ""),
      title: field("title"),
      description: field("description"),
      date: field("date"),
      draft: /^draft: true$/m.test(frontmatter),
      cover: /^cover:$/m.test(frontmatter),
      opening,
      sections: body.split("\n").filter((line) => line.startsWith("## ")).length,
    };
  });

const published = sourcePosts.filter((post) => !post.draft);
const drafts = sourcePosts.filter((post) => post.draft);
const postUrl = (post: SourcePost) => `${ORIGIN}/blog/${post.slug}/`;
const newestFirst = (posts: SourcePost[]) => [...posts].sort((a, b) => b.date.localeCompare(a.date));

/** The list page's post links, in page order. */
function listedPosts(site: BuiltSite) {
  return [...site.read("blog/index.html").matchAll(/<a href="\/blog\/([^"/]+)\/" class="site-post-card-link">/g)].map((match) => match[1]);
}

/** The feed's items: title and link, in feed order. */
function feedItems(site: BuiltSite) {
  return [...site.read("rss.xml").matchAll(/<item><title>([^<]*)<\/title><link>([^<]*)<\/link>/g)].map(([, title, link]) => ({ title, link }));
}

describe("blog in the production build", () => {

  it("publishes no draft: no page, no card, no feed item, no sitemap entry", () => {
    const pages = sitemapPages(dist);
    for (const post of drafts) {
      assert.ok(!dist.has(`blog/${post.slug}/index.html`), `draft ${post.slug} has a page`);
      assert.ok(!listedPosts(dist).includes(post.slug), `draft ${post.slug} is listed`);
      assert.ok(!dist.read("rss.xml").includes(postUrl(post)), `draft ${post.slug} is in the feed`);
      assert.ok(!pages.includes(postUrl(post)), `draft ${post.slug} is in the sitemap`);
      assert.ok(!dist.read("blog/index.html").includes(post.title), `draft ${post.slug}'s title is on the list page`);
    }
  });

  it("lists every published post, newest first, in the list, the feed and the sitemap", () => {
    assert.deepEqual(listedPosts(dist), newestFirst(published).map((post) => post.slug));
    assert.deepEqual(feedItems(dist).map((item) => item.link), newestFirst(published).map(postUrl));
    const pages = sitemapPages(dist);
    for (const url of [`${ORIGIN}/blog/`, ...published.map(postUrl)]) assert.ok(pages.includes(url), `${url} missing from the sitemap`);
  });

  it("serves a valid RSS 2.0 feed on the production origin, linked from every page", () => {
    const feed = dist.read("rss.xml");
    assert.match(feed, /^<\?xml version="1\.0" encoding="UTF-8"\?><rss version="2\.0"[^>]*><channel>.*<\/channel><\/rss>$/s);
    assert.match(feed, /<channel><title>Shiori 博客<\/title><description>[^<]+<\/description><link>https:\/\/www\.windchant\.online\/blog\/<\/link><language>zh-CN<\/language>/);
    for (const page of ["index.html", "blog/index.html"]) {
      assert.match(dist.read(page), new RegExp(`<link rel="alternate" type="application/rss\\+xml" title="Shiori 博客" href="${ORIGIN}/rss.xml">`));
    }
  });
});

describe("blog posts as rendered (drafts-mode build)", () => {
  for (const post of sourcePosts) {
    describe(post.slug, () => {
      const html = draftsDist.read(`blog/${post.slug}/index.html`);

      it("shows the title, day, byline and the post itself as static HTML", () => {
        assert.ok(html.includes(`<h1 class="site-reading-title site-story-type">${post.title}</h1>`));
        assert.match(html, new RegExp(`<time datetime="${post.date}">\\d{4}年\\d{1,2}月\\d{1,2}日</time>`));
        assert.match(html, /<span>吟风<\/span>/);
        assert.ok(html.includes(`<p>${post.opening}</p>`), "the post's first paragraph is not in the page");
        assert.match(html, /<header class="site-header" data-site-header data-mode="fixed">/);
      });
    });
  }

  it("lists, feeds and maps every post, newest first, each with its summary and day", () => {
    const html = draftsDist.read("blog/index.html");
    assert.deepEqual(listedPosts(draftsDist), newestFirst(sourcePosts).map((post) => post.slug));
    for (const post of sourcePosts) {
      assert.ok(html.includes(`<p class="site-post-card-summary">${post.description}</p>`), `${post.slug} card has no summary`);
      assert.ok(html.includes(`datetime="${post.date}"`), `${post.slug} card has no day`);
    }
    assert.deepEqual(
      feedItems(draftsDist),
      newestFirst(sourcePosts).map((post) => ({ title: post.title, link: postUrl(post) })),
    );
    const pages = sitemapPages(draftsDist);
    for (const post of sourcePosts) assert.ok(pages.includes(postUrl(post)), `${post.slug} missing from the sitemap`);
  });
});
