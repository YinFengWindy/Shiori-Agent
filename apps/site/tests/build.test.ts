import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { NARRATIVE_LINES } from "../src/content/narrative";

/*
 * Assertions on the built site (`astro build` runs first, see the package's
 * `test` script). Reading the emitted files directly is what a crawler that
 * does not execute JavaScript sees, so every check here holds without JS.
 */

const dist = resolve(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const ORIGIN = "https://www.windchant.online";

function readDist(path: string) {
  const file = resolve(dist, path);
  assert.ok(existsSync(file), `expected ${path} in the build output; run \`astro build\` first`);
  return readFileSync(file, "utf8");
}

/** The `content` of the one `<meta>` whose `attribute` equals `key`. */
function metaContent(html: string, attribute: "name" | "property", key: string) {
  const matches = [...html.matchAll(new RegExp(`<meta ${attribute}="${key}" content="([^"]*)"`, "g"))];
  assert.equal(matches.length, 1, `expected exactly one <meta ${attribute}="${key}">`);
  return matches[0][1];
}

/** The output file behind an absolute URL on the site origin. */
function distPathOf(url: string) {
  assert.ok(url.startsWith(`${ORIGIN}/`), `${url} must be on ${ORIGIN}`);
  return url.slice(ORIGIN.length + 1);
}

describe("home page HTML", () => {
  const html = readDist("index.html");

  it("declares the language and a non-empty title and description", () => {
    assert.match(html, /<html lang="zh-CN">/);
    assert.match(html, /<title>Shiori · 让角色走进日常<\/title>/);
    assert.ok(metaContent(html, "name", "description").includes("Personal Agent"));
  });

  it("points canonical and og:url at the site root on the production origin", () => {
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/">`));
    assert.equal(metaContent(html, "property", "og:url"), `${ORIGIN}/`);
  });

  it("carries Open Graph and Twitter card tags with an absolute, emitted image", () => {
    assert.equal(metaContent(html, "property", "og:type"), "website");
    assert.equal(metaContent(html, "property", "og:title"), "Shiori · 让角色走进日常");
    assert.equal(metaContent(html, "property", "og:description"), metaContent(html, "name", "description"));
    const image = metaContent(html, "property", "og:image");
    // JPEG, not WebP: some link previewers cannot render WebP cards.
    assert.match(image, /\.jpe?g$/);
    assert.equal(metaContent(html, "property", "og:image:width"), "1200");
    assert.equal(metaContent(html, "property", "og:image:height"), "630");
    assert.ok(existsSync(resolve(dist, distPathOf(image))), `og:image ${image} is not in the build output`);
    assert.equal(metaContent(html, "name", "twitter:card"), "summary_large_image");
    assert.equal(metaContent(html, "name", "twitter:image"), image);
    assert.match(metaContent(html, "name", "theme-color"), /^#[0-9a-f]{6}$/);
  });

  it("renders the title, slogan and both calls to action as static markup", () => {
    assert.match(html, /<h1><img [^>]*alt="Shiori"/);
    assert.match(html, />让角色走进日常<\/p>/);
    assert.match(html, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/latest"[^>]*>.*?下载 Windows 版<\/a>/s);
    assert.match(html, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent"[^>]*>.*?GitHub<\/a>/s);
  });

  it("carries every narrative line as static text, in script order", () => {
    let from = 0;
    for (const { text } of NARRATIVE_LINES) {
      const at = html.indexOf(`>${text}</p>`, from);
      assert.ok(at >= 0, `narrative line missing or out of order: ${text}`);
      from = at;
    }
  });

  it("links the narrative's skip control to the calls to action", () => {
    const target = html.match(/<a href="#([^"]+)"[^>]*>\s*跳过/)?.[1];
    assert.ok(target, "no skip link in the narrative");
    const section = html.match(new RegExp(`<section id="${target}"[^>]*>(.*?)</section>`, "s"))?.[1];
    assert.ok(section?.includes("下载 Windows 版"), `skip target #${target} is not the CTA section`);
  });

  it("paints with no external stylesheet: every CSS rule is inline", () => {
    assert.doesNotMatch(html, /<link [^>]*rel="stylesheet"/);
    assert.doesNotMatch(html, /@import/);
  });

  it("opens the body with the loader, hidden from the accessibility tree, before the page content", () => {
    const body = html.slice(html.indexOf("<body>") + "<body>".length);
    assert.match(body, /^<div id="site-loader" class="site-loader" aria-hidden="true">/);
    assert.ok(body.indexOf("</svg>") < body.indexOf("<main>"), "the loader's bookmark must come before <main>");
  });

  it("inlines the loader's covering layer, its cap fade and its no-script hiding", () => {
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    const layer = [...styles.matchAll(/\.site-loader\{([^}]*)\}/g)].map((match) => match[1]);
    assert.ok(
      layer.some((rule) => rule.includes("position:fixed") && /animation:site-loader-timeout [^;]*var\(--site-loader-cap\)/.test(rule)),
      "no inline .site-loader rule covers the page and fades at the cap",
    );
    assert.match(styles, /--site-loader-cap:\d/);
    assert.match(styles, /@keyframes site-loader-timeout\{to\{[^}]*visibility:hidden/);
    assert.match(styles, /@media \(scripting:none\)\{\.site-loader\{display:none\}\}/);
    // Reduced motion: no sway (the sparkles stop in the desktop's own block).
    assert.match(styles, /@media \(prefers-reduced-motion:reduce\)[^{]*\{[^@]*\.site-loader-bookmark\{animation:none\}/);
  });

  it("ends the loader from an inline script, not a bundle that may still be downloading", () => {
    const script = html.match(/<div id="site-loader".*?<script>(.*?)<\/script>/s)?.[1];
    assert.ok(script, "no inline <script> follows the loader");
    assert.match(script, /data-first-screen/);
    assert.match(script, /data-leaving/);
    assert.match(html, /<img data-scene-backdrop data-first-screen/);
    assert.match(html, /<img [^>]*data-layer="current" data-first-screen/);
  });

  it("mounts the Vercel Web Analytics component from the shared layout", () => {
    assert.match(html, /<vercel-analytics [^>]*><\/vercel-analytics>/);
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
    const index = readDist("sitemap-index.xml");
    const sitemaps = [...index.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
    assert.ok(sitemaps.length > 0, "sitemap index lists no sitemaps");
    const pages = sitemaps.flatMap((url) =>
      [...readDist(distPathOf(url)).matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]));
    assert.ok(pages.includes(`${ORIGIN}/`), `home page missing from sitemap: ${pages.join(", ")}`);
    for (const page of pages) distPathOf(page);
  });
});
