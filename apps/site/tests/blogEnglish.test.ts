import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ORIGIN,
  breadcrumbsOf,
  dist,
  distPathOf,
  hreflangsOf,
  sectionIndexOf,
  visibleTextOf,
} from "./support/builtSite";
import { publishedPosts, untranslatedPosts } from "./support/sourcePosts";

/*
 * The English blog and changelog (#807) as built: the translated posts
 * under /en/blog/, their feed, the English changelog over the Chinese
 * notes, and how each pairs with its Chinese page. The Chinese blog is
 * covered by blog.test.ts, the home pages by i18nBuild.test.ts.
 */

const englishPosts = publishedPosts("blog-en");
const translated = new Set(englishPosts.map((post) => post.slug));
const untranslated = untranslatedPosts();
const enPostUrl = (slug: string) => `${ORIGIN}/en/blog/${slug}/`;

/** Text as Astro writes it into an element. */
function asHtmlText(text: string) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

/**
 * The Chinese left in an English page's visible text, word by word, after
 * the allowed Chinese is taken out: the app's interface names, quoted
 * 「like this」 and followed at once by their English meaning in brackets
 * (「账号」 (Accounts)), because the app's interface is in Chinese and
 * readers must find them there — a quoted name without its meaning counts
 * as untranslated; elements marked `lang="zh-CN"` (the changelog's notes,
 * shown as written); and the 「中」 of the switch back to Chinese.
 */
function strayChinese(html: string) {
  const withoutChinese = html.replace(/<(\w+)[^>]* lang="zh-CN"[^>]*>.*?<\/\1>/gs, " ");
  return visibleTextOf(withoutChinese)
    .replace(/「[^」]*」(?= \([^)]*\p{Script=Latin}[^)]*\))/gu, " ")
    .split(/\s+/)
    .filter((word) => /\p{Script=Han}/u.test(word) && word !== "中");
}

/** The links within the site in a post's prose: where each leads, and its text. */
function siteLinksOf(html: string) {
  const start = html.indexOf('<div class="site-prose">');
  assert.ok(start >= 0, "the page has no prose");
  const prose = html.slice(start, html.indexOf("</article>"));
  return [...prose.matchAll(/<a href="(\/[^"]*)"[^>]*>(.*?)<\/a>/gs)].map(([, href, label]) => ({ href, label: label.replace(/<[^>]+>/g, "") }));
}

describe("English blog list (#807)", () => {
  const html = dist.read("en/blog/index.html");

  it("lists the translated posts only, newest first, each linked to its English page", () => {
    const listed = [...html.matchAll(/<a href="\/en\/blog\/([^"/]+)\/" class="site-post-card-link">/g)].map((match) => match[1]);
    assert.deepEqual(listed.sort(), [...translated].sort());
    assert.equal(listed.length, englishPosts.length);
    for (const post of englishPosts) {
      assert.ok(html.includes(`<p class="site-post-card-summary">${asHtmlText(post.description)}</p>`), `${post.slug} card has no summary`);
    }
    assert.match(html, /<time class="site-post-card-date" datetime="\d{4}-\d{2}-\d{2}">[A-Z][a-z]+ \d{1,2}, \d{4}<\/time>/);
  });
});

describe("English posts as rendered (#807)", () => {
  for (const post of englishPosts) {
    describe(post.slug, () => {
      const html = dist.read(`en/blog/${post.slug}/index.html`);

      it("links within the site in English where an English page exists, and says so where a link leads to a Chinese page", () => {
        for (const { href, label } of siteLinksOf(html)) {
          const path = href.replace(/#.*$/, "");
          assert.ok(dist.has(distPathOf(`${ORIGIN}${path}`)), `${href} leads nowhere`);
          if (path.startsWith("/en/")) continue;
          assert.ok(!dist.has(distPathOf(`${ORIGIN}/en${path}`)), `${href} has an English page: /en${path}`);
          assert.ok(label.endsWith(" (in Chinese)"), `the link to the Chinese page ${href} does not say so: ${label}`);
        }
      });
    });
  }

  // Every published post is translated as of #811: this checks the next Chinese post published before its translation.
  it("claims no English alternate for an untranslated Chinese post, whose switch leads to the English blog", { skip: untranslated.length === 0 && "every published post is translated" }, () => {
    for (const post of untranslated) {
      const html = dist.read(`blog/${post.slug}/index.html`);
      assert.deepEqual(hreflangsOf(html), [], post.slug);
      assert.ok(!dist.has(`en/blog/${post.slug}/index.html`), `${post.slug} has an English page`);
      assert.match(html, /<a href="\/en\/blog\/" hreflang="en"[^>]*data-lang-switch>EN<\/a>/);
    }
  });
});

describe("English feed (#807)", () => {
  const feed = dist.read("en/rss.xml");

  it("is a valid RSS 2.0 feed of the translated posts, in English, on the production origin", () => {
    assert.match(feed, /^<\?xml version="1\.0" encoding="UTF-8"\?><rss version="2\.0"[^>]*><channel>.*<\/channel><\/rss>$/s);
    assert.match(feed, /<channel><title>Shiori Blog<\/title><description>[^<]+<\/description><link>https:\/\/www\.windchant\.online\/en\/blog\/<\/link><language>en<\/language>/);
    const links = [...feed.matchAll(/<item><title>[^<]*<\/title><link>([^<]*)<\/link>/g)].map((match) => match[1]);
    assert.deepEqual(links.sort(), [...translated].sort().map(enPostUrl));
    assert.equal([...feed.matchAll(/<dc:creator>Yinfeng<\/dc:creator>/g)].length, englishPosts.length);
  });

  it("leaves the Chinese feed Chinese", () => {
    const zhFeed = dist.read("rss.xml");
    assert.match(zhFeed, /<language>zh-CN<\/language>/);
    assert.doesNotMatch(zhFeed, /\/en\/blog\//);
  });
});

describe("English changelog (#807)", () => {
  const html = dist.read("en/changelog/index.html");

  it("indexes the versions in English, with English days and GitHub links, under a Home / Changelog breadcrumb", () => {
    const { aside, inline } = sectionIndexOf(html);
    assert.equal(aside?.title, "Versions");
    assert.equal(inline?.title, "Versions");
    assert.deepEqual(aside?.entries[0], { id: "v0.5.3", label: "v0.5.3", note: "October 10, 2026", level: 0 });
    assert.match(html, /rel="noopener"[^>]*>View on GitHub<\/a>/);
    assert.deepEqual(breadcrumbsOf(html).steps, [
      { label: "Home", href: "/en/#download", current: false },
      { label: "Changelog", href: undefined, current: true },
    ]);
    assert.match(html, /<a href="\/changelog\/" hreflang="zh-CN"[^>]*data-lang-switch>中<\/a>/);
    assert.deepEqual(strayChinese(html), []);
  });
});
