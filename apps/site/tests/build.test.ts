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

  it("carries every narrative line as static text, in script order", () => {
    let from = 0;
    for (const { text } of NARRATIVE_LINES) {
      const at = html.indexOf(`>${text}</p>`, from);
      assert.ok(at >= 0, `narrative line missing or out of order: ${text}`);
      from = at;
    }
  });

  it("closes the narrative with the download call: icon title, slogan, download and GitHub links", () => {
    const at = html.indexOf('id="download"');
    assert.ok(at >= 0, "no #download call in the page");
    const lastLine = NARRATIVE_LINES.at(-1)?.text ?? "";
    assert.ok(html.lastIndexOf(`>${lastLine}</p>`) < at, "the download call must follow the narrative lines in reading order");
    const call = html.slice(at, html.indexOf("site-narrative-snaps", at));
    const icon = call.match(/<h1><img [^>]*src="([^"]+)"[^>]*alt="Shiori"|<h1><img [^>]*alt="Shiori"[^>]*src="([^"]+)"/);
    assert.ok(icon, "the title is the app icon with alt Shiori");
    const iconSrc = icon[1] ?? icon[2];
    assert.ok(existsSync(resolve(dist, iconSrc.replace(/^\//, ""))), `app icon ${iconSrc} is not in the build output`);
    assert.match(call, />让角色走进日常<\/p>/);
    assert.match(call, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/latest"[^>]*>.*?下载 Windows 版<span[^>]*><\/span><\/span><\/a>/s);
    assert.match(call, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent"[^>]*>.*?GitHub<\/a>/s);
  });

  it("has no skip control", () => {
    assert.doesNotMatch(html, /跳过/);
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
