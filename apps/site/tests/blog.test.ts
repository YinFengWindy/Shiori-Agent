import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { type BuiltSite, ORIGIN, breadcrumbsOf, dist, distPathOf, draftsDist, idsOf, metaContent, sectionIndexOf, sitemapPages, topBarHomeHref } from "./support/builtSite";

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
  it("has some posts to check", () => {
    assert.ok(sourcePosts.length > 0);
  });

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

  it("serves the list page with its own title and canonical URL, the bar always there, 博客 marked current", () => {
    const html = dist.read("blog/index.html");
    assert.match(html, /<title>博客 · Shiori<\/title>/);
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/blog/">`));
    assert.match(html, /<header class="site-header" data-site-header data-mode="fixed">/);
    assert.match(html, /<a href="\/blog\/"[^>]* aria-current="page">博客<\/a>/);
    if (published.length === 0) assert.match(html, /<p class="site-blog-empty site-story-type">[^<]+<\/p>/);
  });

  it("leads back home from the list with a 首页 / 博客 breadcrumb and BreadcrumbList data", () => {
    const html = dist.read("blog/index.html");
    assert.deepEqual(breadcrumbsOf(html).steps, [
      { label: "首页", href: "/#download", current: false },
      { label: "博客", href: undefined, current: true },
    ]);
    assert.deepEqual(breadcrumbsOf(html).jsonLd, {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "首页", item: `${ORIGIN}/` },
        { "@type": "ListItem", position: 2, name: "博客", item: `${ORIGIN}/blog/` },
      ],
    });
    assert.equal(topBarHomeHref(html), "/#download");
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

      it("carries its title, description, canonical URL and article Open Graph tags", () => {
        assert.ok(html.includes(`<title>${post.title} · Shiori</title>`));
        assert.equal(metaContent(html, "name", "description"), post.description);
        assert.ok(html.includes(`<link rel="canonical" href="${postUrl(post)}">`));
        assert.equal(metaContent(html, "property", "og:url"), postUrl(post));
        assert.equal(metaContent(html, "property", "og:type"), "article");
        assert.equal(metaContent(html, "property", "og:title"), `${post.title} · Shiori`);
        assert.equal(metaContent(html, "property", "og:description"), post.description);
        assert.equal(metaContent(html, "property", "article:published_time"), post.date);
        assert.equal(metaContent(html, "property", "article:author"), "吟风");
        const image = metaContent(html, "property", "og:image");
        assert.ok(draftsDist.has(distPathOf(image)), `og:image ${image} is not in the build output`);
      });

      it("describes itself as a BlogPosting by 吟风 in structured data", () => {
        const json = html.match(/<script type="application\/ld\+json">(.*?)<\/script>/s)?.[1];
        assert.ok(json, "no JSON-LD");
        const data: unknown = JSON.parse(json);
        assert.ok(typeof data === "object" && data !== null);
        assert.deepEqual(
          { ...data, publisher: undefined, image: undefined },
          {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            headline: post.title,
            description: post.description,
            datePublished: post.date,
            inLanguage: "zh-CN",
            url: postUrl(post),
            mainEntityOfPage: postUrl(post),
            author: { "@type": "Person", name: "吟风" },
            publisher: undefined,
            image: undefined,
          },
        );
      });

      it("leads back up with a 首页 / 博客 / post breadcrumb over the title, and BreadcrumbList data", () => {
        const { steps, jsonLd } = breadcrumbsOf(html);
        assert.deepEqual(steps, [
          { label: "首页", href: "/#download", current: false },
          { label: "博客", href: "/blog/", current: false },
          { label: post.title, href: undefined, current: true },
        ]);
        assert.deepEqual(jsonLd, {
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "首页", item: `${ORIGIN}/` },
            { "@type": "ListItem", position: 2, name: "博客", item: `${ORIGIN}/blog/` },
            { "@type": "ListItem", position: 3, name: post.title, item: postUrl(post) },
          ],
        });
        assert.ok(html.indexOf('aria-label="面包屑"') < html.indexOf("<h1"), "the breadcrumb is not over the title");
        assert.equal(topBarHomeHref(html), "/#download");
      });

      it("lists its sections in a table of contents whose links match the headings' ids one to one", () => {
        const { aside, inline } = sectionIndexOf(html);
        if (post.sections < 2) {
          assert.equal(aside, undefined);
          assert.equal(inline, undefined);
          return;
        }
        assert.ok(aside, "no sticky table of contents");
        assert.ok(inline, "no folded <details> table of contents");
        assert.equal(aside.title, "目录");
        assert.equal(inline.title, "目录");
        assert.deepEqual(inline.entries, aside.entries);
        const prose = html.slice(html.indexOf('<div class="site-prose">'), html.indexOf("</article>"));
        const headings = [...prose.matchAll(/<h2 id="([^"]+)">(.*?)<\/h2>/gs)].map(([, id, text]) => ({ id, label: text.replace(/<[^>]+>/g, "") }));
        assert.equal(headings.length, post.sections);
        assert.deepEqual(
          aside.entries.map(({ id, label }) => ({ id, label })),
          headings,
        );
        const ids = idsOf(html);
        assert.equal(new Set(ids).size, ids.length, "an id is used twice");
      });

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
