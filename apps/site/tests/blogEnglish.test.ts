import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ORIGIN,
  assertDescription,
  breadcrumbsOf,
  dist,
  distPathOf,
  hreflangsOf,
  imgTagsOf,
  isRecord,
  jsonLdOf,
  metaContent,
  pictureAt,
  sectionIndexOf,
  sitemapEntries,
  topBarHomeHref,
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
const chinesePosts = publishedPosts("blog");
const translated = new Set(englishPosts.map((post) => post.slug));
const untranslated = untranslatedPosts();
const enPostUrl = (slug: string) => `${ORIGIN}/en/blog/${slug}/`;
const zhPostUrl = (slug: string) => `${ORIGIN}/blog/${slug}/`;
/** The hreflang links of a page in both languages. */
const pair = (zhUrl: string, enUrl: string) => [
  { hreflang: "zh-CN", href: zhUrl },
  { hreflang: "en", href: enUrl },
  { hreflang: "x-default", href: zhUrl },
];
/** English descriptions: 70–160 characters (#806). */
const ENGLISH_DESCRIPTION = { min: 70, max: 160 };

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

describe("strayChinese", () => {
  it("lets a quoted interface name through only with its English meaning right after it", () => {
    const page = (text: string) => `<body><p>${text}</p></body>`;
    assert.deepEqual(strayChinese(page("Open 「账号」 (Accounts) and 「连接」 (Connect).")), []);
    assert.deepEqual(strayChinese(page("Open 「账号」 and click.")), ["「账号」"]);
    assert.deepEqual(strayChinese(page("Open 「账号」 (见下文).")), ["「账号」", "(见下文)."]);
    assert.deepEqual(strayChinese(page("Left as 未翻译.")), ["未翻译."]);
  });
});

describe("English posts as written (#807, #811)", () => {
  it("translates six published Chinese posts, under their slugs, dated as their originals", () => {
    assert.deepEqual([...translated].sort(), [
      "affection",
      "ai-companion-qq-telegram",
      "ai-companion-vs-chatbot",
      "ai-desktop-pet-voice",
      "come-find-you",
      "long-term-memory",
    ]);
    for (const post of englishPosts) {
      const original = chinesePosts.find((chinese) => chinese.slug === post.slug);
      assert.ok(original, `${post.slug} has no published Chinese original`);
      assert.equal(post.date, original.date, `${post.slug} is not dated as its original`);
    }
  });
});

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

  it("is an English page with its own title, description and canonical URL, paired with the Chinese list", () => {
    assert.match(html, /<html lang="en">/);
    assert.match(html, /<title>Blog · Shiori AI Companion<\/title>/);
    assertDescription(metaContent(html, "name", "description"), ["Shiori", "AI companion", "AI girlfriend", "Personal Agent"], ENGLISH_DESCRIPTION);
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/en/blog/">`));
    assert.deepEqual(hreflangsOf(html), pair(`${ORIGIN}/blog/`, `${ORIGIN}/en/blog/`));
    assert.deepEqual(hreflangsOf(dist.read("blog/index.html")), pair(`${ORIGIN}/blog/`, `${ORIGIN}/en/blog/`));
  });

  it("leads home with a Home / Blog breadcrumb, Blog marked current in the English top bar, the English feed linked", () => {
    assert.deepEqual(breadcrumbsOf(html).steps, [
      { label: "Home", href: "/en/#download", current: false },
      { label: "Blog", href: undefined, current: true },
    ]);
    assert.equal(topBarHomeHref(html), "/en/#download");
    assert.match(html, /<a href="\/en\/blog\/"[^>]* aria-current="page">Blog<\/a>/);
    assert.match(html, /<a href="\/en\/changelog\/"[^>]*>Changelog<\/a>/);
    assert.match(html, new RegExp(`<link rel="alternate" type="application/rss\\+xml" title="Shiori Blog" href="${ORIGIN}/en/rss.xml">`));
    assert.deepEqual(strayChinese(html), []);
  });
});

describe("English posts as rendered (#807)", () => {
  for (const post of englishPosts) {
    describe(post.slug, () => {
      const html = dist.read(`en/blog/${post.slug}/index.html`);
      const url = enPostUrl(post.slug);

      it("carries its English title, description, canonical URL and article Open Graph tags", () => {
        assert.match(html, /<html lang="en">/);
        assert.ok(html.includes(`<title>${asHtmlText(post.title)} · Shiori AI Companion</title>`));
        assert.equal(metaContent(html, "name", "description"), asHtmlText(post.description));
        assertDescription(post.description, ["Shiori", "AI companion"], ENGLISH_DESCRIPTION);
        assert.ok(html.includes(`<link rel="canonical" href="${url}">`));
        assert.equal(metaContent(html, "property", "og:url"), url);
        assert.equal(metaContent(html, "property", "og:type"), "article");
        assert.equal(metaContent(html, "property", "og:locale"), "en_US");
        assert.equal(metaContent(html, "property", "article:author"), "Yinfeng");
      });

      it("pairs with its Chinese original both ways", () => {
        assert.deepEqual(hreflangsOf(html), pair(zhPostUrl(post.slug), url));
        assert.deepEqual(hreflangsOf(dist.read(`blog/${post.slug}/index.html`)), pair(zhPostUrl(post.slug), url));
      });

      it("is a BlogPosting in English by Yinfeng, shared as a 1200×630 JPEG, dated in the sitemap", async () => {
        const data = jsonLdOf(html).find((item) => isRecord(item) && item["@type"] === "BlogPosting");
        assert.ok(isRecord(data));
        assert.equal(data.inLanguage, "en");
        assert.equal(data.url, url);
        assert.equal(data.headline, post.title);
        assert.deepEqual(data.author, { "@type": "Person", name: "Yinfeng" });
        const image = metaContent(html, "property", "og:image");
        assert.equal(data.image, image);
        assert.deepEqual(await pictureAt(dist, image), { format: "jpeg", width: 1200, height: 630 });
        const updated = new Date(`${post.date}T00:00:00Z`).toISOString();
        assert.equal(sitemapEntries(dist).find((entry) => entry.loc === url)?.lastmod, updated);
      });

      it("leads back with a Home / Blog / post breadcrumb, a Contents index and an English byline", () => {
        assert.deepEqual(breadcrumbsOf(html).steps, [
          { label: "Home", href: "/en/#download", current: false },
          { label: "Blog", href: "/en/blog/", current: false },
          { label: asHtmlText(post.title), href: undefined, current: true },
        ]);
        if (post.sections >= 2) {
          const { aside, inline } = sectionIndexOf(html);
          assert.equal(aside?.title, "Contents");
          assert.equal(inline?.title, "Contents");
        }
        assert.match(html, new RegExp(`<time datetime="${post.date}">[A-Z][a-z]+ \\d{1,2}, \\d{4}</time>`));
        assert.match(html, /<span>Yinfeng<\/span>/);
        // The language switch leads to the Chinese original.
        assert.match(html, new RegExp(`<a href="/blog/${post.slug}/" hreflang="zh-CN"[^>]*data-lang-switch>中</a>`));
      });

      it("links within the site in English where an English page exists, and says so where a link leads to a Chinese page", () => {
        for (const { href, label } of siteLinksOf(html)) {
          const path = href.replace(/#.*$/, "");
          assert.ok(dist.has(distPathOf(`${ORIGIN}${path}`)), `${href} leads nowhere`);
          if (path.startsWith("/en/")) continue;
          assert.ok(!dist.has(distPathOf(`${ORIGIN}/en${path}`)), `${href} has an English page: /en${path}`);
          assert.ok(label.endsWith(" (in Chinese)"), `the link to the Chinese page ${href} does not say so: ${label}`);
        }
      });

      it("has no Chinese but the app's interface names it quotes", () => {
        assert.deepEqual(strayChinese(html), []);
        for (const image of imgTagsOf(html)) assert.doesNotMatch(image, /\p{Script=Han}/u, `Chinese alt text: ${image}`);
      });
    });
  }

  it("finds the site links in the prose of the posts that have some", () => {
    // Not every post links within the site (the three of #811 do not), but some must, or the check above proves nothing.
    assert.ok(englishPosts.some((post) => siteLinksOf(dist.read(`en/blog/${post.slug}/index.html`)).length > 0));
  });

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
  const zhHtml = dist.read("changelog/index.html");

  it("is an English page with its own title and description, paired with the Chinese changelog", () => {
    assert.match(html, /<html lang="en">/);
    assert.match(html, /<title>Changelog · Shiori AI Companion<\/title>/);
    assertDescription(metaContent(html, "name", "description"), ["Shiori", "AI companion", "open-source", "Personal Agent", "Windows"], ENGLISH_DESCRIPTION);
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/en/changelog/">`));
    const changelogPair = pair(`${ORIGIN}/changelog/`, `${ORIGIN}/en/changelog/`);
    assert.deepEqual(hreflangsOf(html), changelogPair);
    assert.deepEqual(hreflangsOf(zhHtml), changelogPair);
  });

  it("says under its heading that the notes are in Chinese, and marks them so; the Chinese page says nothing", () => {
    assert.match(html, /<\/h1><p class="site-reading-meta site-changelog-notes-language">Release notes are written in Chinese\.<\/p>/);
    assert.equal([...html.matchAll(/<div class="site-prose" lang="zh-CN">/g)].length, 3);
    assert.match(html, /<h3>新增与改进<\/h3>/);
    assert.doesNotMatch(zhHtml, /<p [^>]*class="[^"]*site-changelog-notes-language/);
    assert.equal([...zhHtml.matchAll(/<div class="site-prose">/g)].length, 3);
  });

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

  it("is in the sitemap with its pair", () => {
    const sitemap = dist.read(distPathOf(`${ORIGIN}/sitemap-0.xml`));
    const entry = sitemap.match(new RegExp(`<url><loc>${ORIGIN}/en/changelog/</loc>(.*?)</url>`, "s"))?.[1] ?? "";
    assert.equal([...entry.matchAll(/<xhtml:link rel="alternate"/g)].length, 3);
    assert.match(entry, /hreflang="x-default" href="https:\/\/www\.windchant\.online\/changelog\/"/);
  });
});
