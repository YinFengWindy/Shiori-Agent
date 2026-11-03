import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { en } from "../src/i18n/en";
import { zh } from "../src/i18n/zh";
import {
  ORIGIN,
  dist as site,
  distPathOf,
  hreflangsOf,
  metaContent,
} from "./support/builtSite";
import { untranslatedPosts } from "./support/sourcePosts";

/*
 * The site in two languages (#806), as the build emits it: the English home
 * page at /en/ — read without JavaScript, as a crawler does — the pages'
 * language pairing (hreflang, the sitemap's alternates), the language
 * switches and the one-time English prompt. The Chinese pages themselves
 * are covered by build.test.ts and blog.test.ts.
 */

const zhHome = site.read("index.html");
const enHome = site.read("en/index.html");

/** Every language switch link of a page: where it leads, what it shows, its name, and whether it is the corner one. */
function languageSwitchesOf(html: string) {
  return [...html.matchAll(/<a href="([^"]+)" hreflang="([^"]+)" class="([^"]*)" aria-label="([^"]+)" title="[^"]+" data-lang-switch>([^<]+)<\/a>/g)].map(
    ([, href, hreflang, className, label, text]) => ({
      href,
      hreflang,
      label,
      text,
      corner: className.includes("site-lang-corner"),
    }),
  );
}

/**
 * A published Chinese post without its English version (#807), if one is
 * left: none is while every post is translated (#811), and the checks of
 * such a page skip until the next post is published before its translation.
 */
const chineseOnlyPost = untranslatedPosts()[0]?.slug;
const noChineseOnlyPost = chineseOnlyPost === undefined && "every published post is translated";
/** Where the Chinese-only post's switch and prompt lead, if there is one: the English blog. */
const chineseOnlyPostTarget = chineseOnlyPost === undefined ? {} : { [`blog/${chineseOnlyPost}/index.html`]: "/en/blog/" };

describe("language pairing (#806)", () => {
  const pair = [
    { hreflang: "zh-CN", href: `${ORIGIN}/` },
    { hreflang: "en", href: `${ORIGIN}/en/` },
    { hreflang: "x-default", href: `${ORIGIN}/` },
  ];

  it("pairs the two home pages with the same hreflang links, x-default on the Chinese one", () => {
    assert.deepEqual(hreflangsOf(zhHome), pair);
    assert.deepEqual(hreflangsOf(enHome), pair);
    assert.equal(metaContent(zhHome, "property", "og:locale"), "zh_CN");
    assert.equal(metaContent(zhHome, "property", "og:locale:alternate"), "en_US");
  });

  it("claims no alternate for a page in Chinese only (a post without its English version, #807)", { skip: noChineseOnlyPost }, () => {
    const html = site.read(`blog/${chineseOnlyPost}/index.html`);
    assert.deepEqual(hreflangsOf(html), []);
    assert.doesNotMatch(html, /og:locale:alternate/);
    assert.match(html, /<html lang="zh-CN">/);
  });

  /** The sitemap's URLs, each with its alternates. */
  const sitemapUrls = () =>
    [...site.read(distPathOf(`${ORIGIN}/sitemap-0.xml`)).matchAll(/<url>(.*?)<\/url>/gs)].map(([, url]) => ({
      loc: url.match(/<loc>([^<]+)<\/loc>/)?.[1],
      links: [...url.matchAll(/<xhtml:link rel="alternate" hreflang="([^"]+)" href="([^"]+)"\/>/g)].map(([, hreflang, href]) => ({ hreflang, href })),
    }));

  it("lists both home pages in the sitemap, each with the pair and x-default as alternates", () => {
    const urls = sitemapUrls();
    for (const home of [`${ORIGIN}/`, `${ORIGIN}/en/`]) {
      assert.deepEqual(urls.find((url) => url.loc === home)?.links, pair, `${home} alternates`);
    }
  });

  it("lists a page in Chinese only in the sitemap without alternates", { skip: noChineseOnlyPost }, () => {
    assert.deepEqual(sitemapUrls().find((url) => url.loc === `${ORIGIN}/blog/${chineseOnlyPost}/`)?.links, []);
  });
});

describe("language switch (#806)", () => {
  it("puts a corner switch and one in the top bar on the Chinese home page, both to the English home page", () => {
    const switches = languageSwitchesOf(zhHome);
    const corner = switches.filter((link) => link.corner);
    assert.equal(corner.length, 1, "one corner switch");
    assert.deepEqual(corner[0], { href: "/en/", hreflang: "en", label: zh.languageSwitch.label, text: "EN", corner: true });
    const bar = zhHome.match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1] ?? "";
    assert.deepEqual(languageSwitchesOf(bar).map(({ href, text, corner: inCorner }) => ({ href, text, inCorner })), [{ href: "/en/", text: "EN", inCorner: false }]);
  });

  it("leads back from the English home page with 「中」", () => {
    const corner = languageSwitchesOf(enHome).filter((link) => link.corner);
    assert.deepEqual(corner, [{ href: "/", hreflang: "zh-CN", label: en.languageSwitch.label, text: "中", corner: true }]);
  });

  it("shows only one pair at a time: the corner pair fades out while the top bar shows; without scripting neither the corner pair nor music in the bar", () => {
    const styles = [...zhHome.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    assert.match(styles, /:root:has\(\.site-header\[data-revealed\]\) \.site-corner-controls\{[^}]*visibility:hidden/);
    assert.match(styles, /@media \(scripting:none\)\{\.site-corner-controls\{display:none\}\}/);
    assert.match(styles, /@media \(scripting:none\)\{[^}]*\}\.site-header-sound\{display:none\}\}/);
  });

  it("keeps the corner controls and the English prompt under the loader, which lets no click through (#810)", () => {
    const styles = [...zhHome.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    assert.match(styles, /\.site-corner-controls\{[^}]*z-index:var\(--site-layer-corner\)/);
    assert.match(styles, /\.site-lang-prompt\{[^}]*z-index:var\(--site-layer-corner\)/);
    assert.match(styles, /\.site-loader\{[^}]*z-index:var\(--site-layer-loader\)/);
    const layer = (name: string) => Number(styles.match(new RegExp(`--site-layer-${name}:(\\d+)`))?.[1]);
    assert.ok(layer("corner") < layer("loader"), "the corner controls must sit under the loader");
    assert.doesNotMatch(styles, /over-loader/);
    // The prompt waits for the loader to go, so its entrance plays in view.
    assert.match(styles, /:root\[data-site-loader\] \.site-lang-prompt\{display:none\}/);
    // Nothing is marked to pass the loader's input guard.
    for (const home of [zhHome, enHome]) assert.doesNotMatch(home, /passthrough/);
  });

  it("puts the switch in the top bar of the reading pages, to the same page in English, or the English blog for an untranslated post (#807)", () => {
    const targets = {
      "blog/index.html": "/en/blog/",
      "changelog/index.html": "/en/changelog/",
      "blog/ai-companion-vs-chatbot/index.html": "/en/blog/ai-companion-vs-chatbot/",
      "blog/affection/index.html": "/en/blog/affection/",
      ...chineseOnlyPostTarget,
    };
    for (const [page, href] of Object.entries(targets)) {
      const switches = languageSwitchesOf(site.read(page));
      assert.deepEqual(switches.map((link) => ({ href: link.href, text: link.text, corner: link.corner })), [{ href, text: "EN", corner: false }], page);
    }
  });
});

describe("English prompt (#806)", () => {
  /** The prompt of a page, if it has one. */
  const promptOf = (html: string) => html.match(/<aside class="site-lang-prompt"[^>]*>.*?<\/aside>/s)?.[0];

  it("ships hidden on every Chinese page, in English, with Switch to the English page and Dismiss", () => {
    const targets = {
      "index.html": "/en/",
      "blog/index.html": "/en/blog/",
      "changelog/index.html": "/en/changelog/",
      "blog/affection/index.html": "/en/blog/affection/",
      ...chineseOnlyPostTarget,
    };
    for (const [page, href] of Object.entries(targets)) {
      const prompt = promptOf(site.read(page));
      assert.ok(prompt, `${page} has no prompt`);
      assert.match(prompt, /^<aside class="site-lang-prompt" lang="en" aria-label="Language" data-lang-prompt hidden>/);
      assert.match(prompt, />View this site in English\?<\/p>/);
      assert.match(prompt, /<button type="button"[^>]*data-lang-prompt-dismiss>Dismiss<\/button>/);
      assert.ok(prompt.includes(`<a href="${href}" hreflang="en"`), `${page}'s prompt does not lead to ${href}`);
      assert.match(prompt, /data-lang-switch data-lang-prompt-switch>Switch<\/a>/);
    }
  });
});
