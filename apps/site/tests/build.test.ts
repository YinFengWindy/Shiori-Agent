import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";
import { GALLERY_ARTS } from "../src/content/gallery";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { SHOWCASE_CLIP_IDS } from "../src/content/showcase";
import { zh } from "../src/i18n/zh";
import {
  ORIGIN,
  dist as site,
  distPathOf,
  imgTagsOf,
  sitemapPages,
} from "./support/builtSite";
import { runLoaderGate } from "./support/loaderGate";

/*
 * Assertions on the built site (`astro build` runs first, see the package's
 * `test` script). Reading the emitted files directly is what a crawler that
 * does not execute JavaScript sees, so every check here holds without JS.
 * The blog's pages are covered by blog.test.ts, the English home page and
 * the language switch by i18nBuild.test.ts.
 */

/** The Chinese showcase blocks, in page order. */
const SHOWCASE_FEATURES = SHOWCASE_CLIP_IDS.map((clip) => ({ clip, ...zh.showcase.features[clip] }));

const dist = site.dir;
const readDist = site.read;

describe("home page HTML", () => {
  const html = readDist("index.html");

  it("has one h1, the app icon (decorative) with the keyword title as its visually hidden text (#799)", () => {
    const headings = [...html.matchAll(/<h1[ >].*?<\/h1>/gs)].map((match) => match[0]);
    assert.equal(headings.length, 1);
    assert.match(
      headings[0],
      /^<h1><img src="\/icons\/icon-512\.png"[^>]* alt=""[^>]*><span class="sr-only">Shiori：会慢慢喜欢上你的 AI 伴侣，开源的 Personal Agent<\/span><\/h1>$/,
    );
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    assert.match(styles, /\.sr-only\{[^}]*position:absolute/);
  });

  it("writes an alt attribute out on every picture: empty for decoration, words for the rest (#799)", () => {
    const images = imgTagsOf(html);
    assert.ok(images.length > 0);
    for (const image of images) assert.match(image, / alt="[^"]*"/, `no alt="…" on ${image}`);
    // Words for what carries something: the narrative's CGs, the showcase stills, the strip's own prints.
    const narrativeCgs = new Set(NARRATIVE_LINES.flatMap((line) => (line.cg ? [line.cg] : [])));
    const described = images.filter((image) => / alt="[^"]+"/.test(image));
    assert.equal(described.length, narrativeCgs.size + SHOWCASE_FEATURES.length + GALLERY_ARTS.length);
  });

  it("closes the narrative with the download call: icon title, slogan, download and GitHub links", () => {
    const at = html.indexOf('id="download"');
    assert.ok(at >= 0, "no #download call in the page");
    const lastId = NARRATIVE_LINES.at(-1)?.id;
    const lastLine = lastId ? zh.narrative.lines[lastId] : "";
    assert.ok(html.lastIndexOf(`>${lastLine}</p>`) < at, "the download call must follow the narrative lines in reading order");
    const call = html.slice(at, html.indexOf("site-narrative-snaps", at));
    const iconSrc = call.match(/<h1><img src="([^"]+)"/)?.[1];
    assert.ok(iconSrc, "the title is the app icon");
    assert.ok(existsSync(resolve(dist, iconSrc.replace(/^\//, ""))), `app icon ${iconSrc} is not in the build output`);
    assert.match(call, />把我带回家吧，笨蛋。<\/p>/);
    assert.match(call, />会慢慢喜欢上你的 AI 伴侣<\/p>/);
    assert.match(call, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/latest"[^>]*>.*?下载 Windows 版<span[^>]*><\/span><\/span><\/a>/s);
    assert.match(call, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent"[^>]*>.*?GitHub<\/a>/s);
  });

  it("opens the body with the loader, hidden from the accessibility tree, before the page content", () => {
    const body = html.slice(html.indexOf("<body>") + "<body>".length);
    assert.match(body, /^<div id="site-loader" class="site-loader" aria-hidden="true"/);
    assert.ok(body.indexOf("site-loader-progress") < body.indexOf("<main>"), "the loader must come before <main>");
  });

  it("leaves the loader out on Back / Forward and anchored visits from the first frame: a head gate, a CSS hide, a script that stands down (#797)", () => {
    const head = html.slice(0, html.indexOf("</head>"));
    const gate = head.match(/<script>(.*?)<\/script>/s);
    assert.ok(gate, "no inline gate script in the head");
    // The built gate itself decides: marked on Back / Forward and with an anchor only.
    assert.deepEqual(runLoaderGate(gate[1], { navigationType: "navigate", hash: "" }), []);
    assert.deepEqual(runLoaderGate(gate[1], { navigationType: "back_forward", hash: "" }), ["data-site-loader-skip"]);
    assert.deepEqual(runLoaderGate(gate[1], { navigationType: "navigate", hash: "#download" }), ["data-site-loader-skip"]);
    assert.ok(head.indexOf(gate[0]) < head.indexOf("<style>"), "the gate must run before the stylesheet can paint the loader");
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    assert.match(styles, /html\[data-site-loader-skip\] \.site-loader\{display:none\}/);
    const script = html.match(/<div id="site-loader".*?<script>(.*?)<\/script>/s)?.[1] ?? "";
    assert.match(script, /hasAttribute\("data-site-loader-skip"\)\)\s*\{\s*loader\.remove\(\)/);
  });

  describe("top bar (#773)", () => {
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");

    it("shares one direct-download script with the closing call: the release API is asked once", () => {
      assert.equal([...html.matchAll(/<a [^>]*data-download-installer>/g)].length, 2);
      assert.equal(html.split("https://api.github.com/repos/YinFengWindy/Shiori-Agent/releases/latest").length - 1, 1);
    });

    it("starts out of sight above the page, shows without scripting, and does not slide under reduced motion", () => {
      assert.match(styles, /\.site-header\[data-mode=reveal\]\{[^}]*visibility:hidden[^}]*translate:0 -100%/);
      assert.match(styles, /@media \(scripting:none\)\{\.site-header\[data-mode=reveal\]\{visibility:visible;translate:none\}/);
      assert.match(
        styles,
        /@media \(prefers-reduced-motion:reduce\)\{\.site-header\[data-mode=reveal\],\.site-header\[data-mode=reveal\]\[data-revealed\],[^{]*\{transition:none\}/,
      );
    });
  });
});

describe("crawler files", () => {
  it("robots.txt allows crawling and names the emitted sitemap index by absolute URL", () => {
    const robots = readDist("robots.txt");
    assert.match(robots, /^User-agent: \*$/m);
    assert.match(robots, /^Allow: \/$/m);
    const sitemap = robots.match(/^Sitemap: (\S+)$/m)?.[1];
    assert.equal(sitemap, `${ORIGIN}/sitemap-index.xml`);
    readDist(distPathOf(sitemap));
  });

  it("the sitemap lists the home page, and only production-origin URLs", () => {
    const pages = sitemapPages(site);
    assert.ok(pages.includes(`${ORIGIN}/`), `home page missing from sitemap: ${pages.join(", ")}`);
    for (const page of pages) distPathOf(page);
  });
});

/*
 * The changelog page as `site:test` builds it: from tests/fixtures/releases.json
 * (tests/fixtures/changelog.env), so the expected releases are known here.
 * The notes' clean-up itself is unit-tested in changelog.test.ts.
 */
describe("changelog page (#792)", () => {
  const html = readDist("changelog/index.html");

  it("lists the published full releases newest first, each with its day, GitHub link and notes as static HTML", () => {
    assert.equal([...html.matchAll(/<h1[ >]/g)].length, 1);
    const versions = [...html.matchAll(/<h2 class="site-reading-title site-story-type" id="(v[^"]+)-title">/g)].map((match) => match[1]);
    assert.deepEqual(versions, ["v0.5.3", "v0.5.2", "v0.1.0"]);
    assert.match(html, /<time datetime="2026-10-09T16:41:11\.000Z">2026年10月10日<\/time>/);
    assert.match(html, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/tag\/v0\.5\.2" rel="noopener"[^>]*>GitHub 上查看<\/a>/);
    assert.match(html, /<h3>新增与改进<\/h3>/);
    assert.match(html, /<strong>角色好感度<\/strong>/);
    assert.match(html, /<h3>已知问题<\/h3>/);
  });

  it("leaves out drafts, prereleases, the notes' repeated version headings, comments and 下载 sections", () => {
    assert.doesNotMatch(html, /v0\.6\.0/);
    assert.doesNotMatch(html, /Shiori v0\.5\.2|shiori-daily-release/);
    assert.doesNotMatch(html, /<h\d[^>]*>下载<\/h\d>|Shiori-Setup-0\.5\.2\.exe|Shiori\.Setup\.0\.1\.0\.exe|SHA256SUMS/);
  });

  it("runs none of the notes' own markup: no script, event handler or javascript: link", () => {
    // The notes alone: the page's own scripts (breadcrumb data, the index) sit outside them.
    const notes = [...html.matchAll(/<div class="site-prose">(.*?)<\/div><\/article>/gs)].map((match) => match[1]).join("\n");
    assert.equal([...html.matchAll(/<div class="site-prose">/g)].length, 3);
    // Real tags only: the escaped text may spell `onerror=` or `javascript:` harmlessly.
    assert.doesNotMatch(notes, /<(script|img)\b|<[a-z][^>]*\son\w+=|<[a-z][^>]*\s(href|src)="[^"]*javascript:/i);
    assert.ok(notes.includes("&lt;script&gt;alert(1)&lt;/script&gt;"), "the notes' script tag is not shown as text");
  });

  it("marks the notes' links off the site rel=noopener", () => {
    const notes = html.slice(html.indexOf('<div class="site-prose">'), html.indexOf("</main>"));
    const links = [...notes.matchAll(/<a href="(https?:[^"]+)"([^>]*)>/g)].filter(([, href]) => !href.startsWith(ORIGIN));
    assert.ok(links.length > 0);
    for (const [, href, rest] of links) assert.match(rest, /rel="noopener"/, `${href} has no rel=noopener`);
  });
});
