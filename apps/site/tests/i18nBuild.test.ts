import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { GALLERY_ARTS } from "../src/content/gallery";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { SHOWCASE_CLIP_IDS } from "../src/content/showcase";
import { en } from "../src/i18n/en";
import { zh } from "../src/i18n/zh";
import { controlButtonClass } from "../src/lib/controlButton";
import {
  ORIGIN,
  assertDescription,
  breadcrumbsOf,
  dist as site,
  distPathOf,
  hreflangsOf,
  imgTagsOf,
  isRecord,
  jsonLdOf,
  metaContent,
  topBarHomeHref,
  visibleTextOf,
} from "./support/builtSite";
import { runLoaderGate } from "./support/loaderGate";

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

/** The classes of a stretch of page's language switch links and music switch buttons, in document order. */
function controlClassesOf(html: string) {
  return [
    ...html.matchAll(
      /<a href="[^"]+" hreflang="[^"]+" class="([^"]*)"[^>]* data-lang-switch>|<button type="button" aria-pressed="false" aria-label="[^"]+" title="[^"]+" class="([^"]*)">/g,
    ),
  ].map(([, language, music]) => (language === undefined ? { music } : { language }));
}

/** Text as Astro writes it into an element: `&`, `<`, `>` and quotes escaped. */
function asHtmlText(text: string) {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

/** Chinese characters. */
const CJK = /\p{Script=Han}/u;

describe("English home page (#806)", () => {
  it("declares English and carries the English title and description with the English search words", () => {
    assert.match(enHome, /^<!DOCTYPE html><html lang="en">/);
    assert.match(enHome, /<title>Shiori · The AI Companion Who Grows to Like You · Open-Source Personal Agent<\/title>/);
    assertDescription(
      metaContent(enHome, "name", "description"),
      ["Shiori", "AI companion", "AI girlfriend", "open-source", "Personal Agent", "desktop AI", "Windows"],
      { min: 70, max: 160 },
    );
  });

  it("points canonical and og:url at itself, with English Open Graph tags", () => {
    assert.match(enHome, new RegExp(`<link rel="canonical" href="${ORIGIN}/en/">`));
    assert.equal(metaContent(enHome, "property", "og:url"), `${ORIGIN}/en/`);
    assert.equal(metaContent(enHome, "property", "og:locale"), "en_US");
    assert.equal(metaContent(enHome, "property", "og:locale:alternate"), "zh_CN");
    assert.equal(metaContent(enHome, "property", "og:title"), en.meta.homeTitle);
    assert.equal(metaContent(enHome, "property", "og:description"), metaContent(enHome, "name", "description"));
    assert.equal(metaContent(enHome, "property", "og:image:alt"), en.art["cg-6"]);
    // The same share picture as the Chinese page.
    assert.equal(metaContent(enHome, "property", "og:image"), metaContent(zhHome, "property", "og:image"));
  });

  it("describes the site and the app in English under its own URL, published by the same organization", () => {
    const [data] = jsonLdOf(enHome);
    assert.ok(isRecord(data) && Array.isArray(data["@graph"]));
    const graph = data["@graph"].filter(isRecord);
    const byType = (type: string) => graph.find((item) => item["@type"] === type);
    const website = byType("WebSite");
    const app = byType("SoftwareApplication");
    const organization = byType("Organization");
    assert.ok(website && app && organization);
    for (const item of [website, app]) {
      assert.equal(item.inLanguage, "en");
      assert.equal(item.url, `${ORIGIN}/en/`);
      assert.equal(item.description, metaContent(enHome, "name", "description"));
    }
    assert.equal(website["@id"], `${ORIGIN}/en/#website`);
    assert.equal(app["@id"], `${ORIGIN}/en/#software`);
    assert.equal(organization["@id"], `${ORIGIN}/#organization`);
  });

  it("carries every narrative line in English as static text, in order, each under its anchor", () => {
    let from = 0;
    for (const line of NARRATIVE_LINES) {
      const at = enHome.indexOf(`<p class="site-narrative-line site-story-type" data-narrative-line data-anchor="${line.id}"`, from);
      assert.ok(at >= 0, `narrative line ${line.id} missing, out of order or without its anchor`);
      assert.ok(enHome.indexOf(`>${asHtmlText(en.narrative.lines[line.id])}</p>`, at) >= 0, `English line ${line.id} missing`);
      from = at;
    }
    assert.match(enHome, /<p class="site-dialogue-name site-story-type">Yinfeng<\/p>/);
  });

  it("anchors each line at its step's snap point, in the page flow, the download step at the download call (both languages)", () => {
    for (const html of [zhHome, enHome]) {
      const snaps = html.match(/<div class="site-narrative-snaps" aria-hidden="true">(.*?)<\/div><\/section>/s)?.[1] ?? "";
      const ids = [...snaps.matchAll(/<div class="site-narrative-snap"( id="([^"]+)")?><\/div>/g)].map((match) => match[2]);
      assert.deepEqual(ids, [...NARRATIVE_LINES.map((line) => line.id), undefined]);
      assert.match(html, /<div id="download" class="site-download" data-narrative-download>/);
    }
  });

  it("closes the narrative with the English call: hidden keyword heading, headline, slogan and download button", () => {
    const at = enHome.indexOf('id="download"');
    const call = enHome.slice(at, enHome.indexOf("site-narrative-snaps", at));
    assert.match(call, /<span class="sr-only">Shiori: the AI companion who grows to like you, an open-source Personal Agent<\/span>/);
    assert.match(call, />Take me home already, dummy\.<\/p>/);
    assert.match(call, />The AI companion who grows to like you<\/p>/);
    assert.match(call, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/latest"[^>]*>.*?Download for Windows<span[^>]*><\/span><\/span><\/a>/s);
  });

  it("shows the showcase in English over the same screenshots, and the photo strip with English alt text", () => {
    for (const clip of SHOWCASE_CLIP_IDS) {
      const feature = en.showcase.features[clip];
      assert.ok(enHome.includes(`<h2 class="site-feature-title site-story-type">${asHtmlText(feature.title)}</h2>`), `${clip} title`);
      assert.ok(enHome.includes(`>${asHtmlText(feature.line)}</p>`), `${clip} line`);
      assert.ok(enHome.includes(` alt="${feature.stillAlt}"`), `${clip} still alt`);
    }
    assert.match(enHome, /<section class="site-showcase" aria-label="Shiori features">/);
    assert.match(enHome, /<div class="site-photostrip" role="region" aria-label="Yinfeng's CG photos"/);
    const prints = [...enHome.matchAll(/<li class="site-photo"><img ([^>]*)><\/li>/g)].map(([, img]) => img.match(/ alt="([^"]*)"/)?.[1]);
    assert.deepEqual(prints, GALLERY_ARTS.map((art) => en.art[art]));
    // The stills are the Chinese page's.
    const stills = (html: string) => [...html.matchAll(/<img class="site-feature-still" src="([^"]+)"/g)].map((match) => match[1]);
    assert.deepEqual(stills(enHome), stills(zhHome));
  });

  it("has no Chinese left in its text or alt text, but for the 「中」 of the switch back", () => {
    const stray = visibleTextOf(enHome)
      .split(/\s+/)
      .filter((word) => CJK.test(word) && word !== "中");
    assert.deepEqual(stray, []);
    for (const image of imgTagsOf(enHome)) assert.doesNotMatch(image, CJK, `Chinese alt text: ${image}`);
  });

  it("labels the top bar, footer and music switch in English, and leads home to the English download state", () => {
    assert.equal(topBarHomeHref(enHome), "/en/#download");
    assert.match(enHome, /<nav class="site-header-bar" aria-label="Site navigation">/);
    assert.match(enHome, /<a href="\/en\/blog\/"[^>]*>Blog<\/a>/);
    assert.match(enHome, /<a href="\/en\/changelog\/"[^>]*>Changelog<\/a>/);
    // The bar's narrow space has the short download label.
    const bar = enHome.match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1] ?? "";
    assert.match(bar, /data-download-installer>.*?<span>Download<span data-download-version><\/span><\/span><\/a>/s);
    const footer = enHome.match(/<footer class="site-footer">(.*?)<\/footer>/s)?.[1] ?? "";
    assert.match(footer, /<nav aria-label="Project links"/);
    assert.match(footer, />Releases<\/a>/);
    assert.match(footer, />MIT License<\/a>/);
    assert.match(enHome, /aria-label="Background music"/);
    assert.match(enHome, /title="Play background music"/);
  });

  it("keeps the loader and its gate: an anchored visit (the switch's) skips it", () => {
    const head = enHome.slice(0, enHome.indexOf("</head>"));
    const gate = head.match(/<script>(.*?)<\/script>/s);
    assert.ok(gate);
    assert.deepEqual(runLoaderGate(gate[1], { navigationType: "navigate", hash: "#remembers" }), ["data-site-loader-skip"]);
    assert.match(enHome, /<body><div id="site-loader" class="site-loader" aria-hidden="true"/);
  });
});

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

  it("claims no alternate for a page in Chinese only (a post without its English version, #807)", () => {
    for (const page of ["blog/affection/index.html"]) {
      const html = site.read(page);
      assert.deepEqual(hreflangsOf(html), [], page);
      assert.doesNotMatch(html, /og:locale:alternate/, page);
      assert.match(html, /<html lang="zh-CN">/, page);
    }
  });

  it("lists both home pages in the sitemap, each with the pair and x-default as alternates; single-language pages without", () => {
    const sitemap = site.read(distPathOf(`${ORIGIN}/sitemap-0.xml`));
    const urls = [...sitemap.matchAll(/<url>(.*?)<\/url>/gs)].map(([, url]) => ({
      loc: url.match(/<loc>([^<]+)<\/loc>/)?.[1],
      links: [...url.matchAll(/<xhtml:link rel="alternate" hreflang="([^"]+)" href="([^"]+)"\/>/g)].map(([, hreflang, href]) => ({ hreflang, href })),
    }));
    for (const home of [`${ORIGIN}/`, `${ORIGIN}/en/`]) {
      assert.deepEqual(urls.find((url) => url.loc === home)?.links, pair, `${home} alternates`);
    }
    assert.deepEqual(urls.find((url) => url.loc === `${ORIGIN}/blog/affection/`)?.links, []);
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

  it("gives the language and music switches one look, side by side in the corner and in the top bar, before the download button (#810)", () => {
    for (const home of [zhHome, enHome]) {
      const corner = home.match(/<div class="site-corner-controls">(.*?)<\/astro-island><\/div>/s)?.[1] ?? "";
      assert.deepEqual(controlClassesOf(corner), [{ language: `${controlButtonClass} site-lang-corner` }, { music: controlButtonClass }]);
      const bar = home.match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1] ?? "";
      assert.deepEqual(controlClassesOf(bar), [{ language: controlButtonClass }, { music: `${controlButtonClass} site-header-sound` }]);
      assert.ok(bar.indexOf('component-export="SoundToggle"') < bar.indexOf("data-download-installer"), "the switches come before the download button");
    }
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

  it("on phones swaps the download button and the text GitHub link for a GitHub tile in the switches' look, on every page (#814)", () => {
    const github = "https://github.com/YinFengWindy/Shiori-Agent";
    for (const page of ["index.html", "en/index.html", "blog/index.html", "en/blog/index.html", "changelog/index.html", "en/changelog/index.html"]) {
      const bar = site.read(page).match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1] ?? "";
      const githubLinks = [...bar.matchAll(new RegExp(`<a href="${github}" class="([^"]*)"([^>]*)>`, "g"))].map(([, className, rest]) => ({ className, rest }));
      assert.deepEqual(
        githubLinks.map(({ className }) => className.split(" ").filter((name) => name.endsWith(":hidden"))),
        [["max-md:hidden"], ["md:hidden"]],
        `${page}: the text link off on phones, the tile only on them`,
      );
      assert.equal(githubLinks[1].className, `${controlButtonClass} md:hidden`, page);
      assert.match(githubLinks[1].rest, /aria-label="GitHub"/, page);
      assert.match(bar, /<a href="[^"]+" class="[^"]* max-md:hidden" data-download-installer>/, `${page}: no download button on phones`);
    }
  });

  it("plays no music on the reading pages: their top bar has the language switch only", () => {
    for (const page of ["blog/index.html", "changelog/index.html", "en/blog/index.html"]) {
      const bar = site.read(page).match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1] ?? "";
      assert.deepEqual(controlClassesOf(bar), [{ language: controlButtonClass }], page);
    }
  });

  it("puts the switch in the top bar of the reading pages, to the same page in English, or the English blog for an untranslated post (#807)", () => {
    const targets = {
      "blog/index.html": "/en/blog/",
      "changelog/index.html": "/en/changelog/",
      "blog/ai-companion-vs-chatbot/index.html": "/en/blog/ai-companion-vs-chatbot/",
      "blog/affection/index.html": "/en/blog/",
    };
    for (const [page, href] of Object.entries(targets)) {
      const switches = languageSwitchesOf(site.read(page));
      assert.deepEqual(switches.map((link) => ({ href: link.href, text: link.text, corner: link.corner })), [{ href, text: "EN", corner: false }], page);
    }
  });

  it("keeps the breadcrumb in the page's language", () => {
    assert.deepEqual(breadcrumbsOf(site.read("changelog/index.html")).steps[0], { label: "首页", href: "/#download", current: false });
  });
});

describe("English prompt (#806)", () => {
  /** The prompt of a page, if it has one. */
  const promptOf = (html: string) => html.match(/<aside class="site-lang-prompt"[^>]*>.*?<\/aside>/s)?.[0];

  it("ships hidden on every Chinese page, in English, with Switch to the English page and Dismiss", () => {
    const targets = { "index.html": "/en/", "blog/index.html": "/en/blog/", "changelog/index.html": "/en/changelog/", "blog/affection/index.html": "/en/blog/" };
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

  it("is driven by a script that asks once and remembers the answer", () => {
    assert.match(zhHome, /shiori-site-language-prompt/);
    assert.match(zhHome, /navigator\.languages/);
  });

  it("is not on the English page", () => {
    assert.equal(promptOf(enHome), undefined);
    assert.doesNotMatch(enHome, /data-lang-prompt/);
  });
});
