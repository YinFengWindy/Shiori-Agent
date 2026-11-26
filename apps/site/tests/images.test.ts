import assert from "node:assert/strict";
import { readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { dist, draftsDist, imgTagsOf, type BuiltSite } from "./support/builtSite";

/**
 * Every picture a built page can request (an `<img>` / `<source>`, a
 * preload, an icon, an Open Graph image, a CSS `url()`, or a `data-src` the
 * narrative and the QQ card assign later). A missing file is a broken
 * image; a file past the budget is the transfer that stalls on the mainland
 * CDN in front of the site (uncached responses from about 500 KB up).
 */
const IMAGE_BYTE_BUDGET = 200 * 1024;

/** The loader illustration plus the two pictures the first frame waits for. */
const FIRST_SCREEN_BYTE_BUDGET = 450 * 1024;

const IMAGE_URL = /\.(?:png|jpe?g|webp|gif|avif|svg|ico)(?:$|\?)/i;

function htmlPages(site: BuiltSite): { path: string; html: string }[] {
  const pages: { path: string; html: string }[] = [];
  const walk = (dir: string, prefix: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(resolve(dir, entry.name), path);
      else if (entry.name.endsWith(".html")) pages.push({ path, html: site.read(path) });
    }
  };
  walk(site.dir, "");
  return pages;
}

/** Image URLs in one page, without the origin and without a query. */
function imageUrls(html: string): string[] {
  const urls: string[] = [];
  const add = (value: string | undefined) => {
    if (!value) return;
    for (const part of value.split(",")) {
      const token = part.trim().split(/\s+/)[0];
      if (!token || token.startsWith("data:") || token.startsWith("#")) continue;
      urls.push(token);
    }
  };
  for (const tag of html.match(/<(?:img|source)\b[^>]*>/g) ?? []) {
    for (const attr of tag.matchAll(/\b(?:data-src|data-dusk|data-night|src|srcset)="([^"]*)"/g)) add(attr[1]);
  }
  for (const tag of html.match(/<link\b[^>]*>/g) ?? []) {
    const rel = tag.match(/\brel="([^"]*)"/)?.[1] ?? "";
    const asImage = /\bas="image"/.test(tag);
    if (rel.split(/\s+/).includes("preload") && asImage) add(tag.match(/\bhref="([^"]*)"/)?.[1]);
    if (/(?:^|\s)(?:icon|apple-touch-icon)(?:\s|$)/.test(rel)) add(tag.match(/\bhref="([^"]*)"/)?.[1]);
  }
  for (const content of html.matchAll(/<meta property="og:image" content="([^"]*)"/g)) add(content[1]);
  for (const style of html.matchAll(/<style[^>]*>(.*?)<\/style>/gs)) {
    for (const url of style[1].matchAll(/url\(([^)]+)\)/g)) add(url[1].trim().replace(/^["']|["']$/g, ""));
  }
  return urls;
}

function localPath(url: string): string | undefined {
  if (url.startsWith("https://www.windchant.online/")) return url.slice("https://www.windchant.online".length);
  if (url.startsWith("/")) return url;
  return undefined;
}

function assertImagesResolve(site: BuiltSite) {
  const pages = htmlPages(site);
  assert.ok(pages.length > 0);
  const files = new Map<string, number>();
  for (const { path, html } of pages) {
    for (const url of imageUrls(html)) {
      assert.ok(!url.includes("undefined") && !/\bnull\b/.test(url) && !url.includes("_astro/_astro") && !url.startsWith("//"), `${path} has a malformed image URL ${url}`);
      const local = localPath(url.split("#")[0].split("?")[0]);
      if (!local) {
        assert.ok(!IMAGE_URL.test(url), `${path} points an image at ${url}`);
        continue;
      }
      const file = resolve(site.dir, local.replace(/^\//, ""));
      assert.ok(statSync(file, { throwIfNoEntry: false })?.isFile(), `${path} requests ${url}, missing from the build`);
      files.set(local, statSync(file).size);
    }
  }
  for (const [path, bytes] of files) {
    assert.ok(bytes <= IMAGE_BYTE_BUDGET, `${path} is ${bytes} bytes, over the ${IMAGE_BYTE_BUDGET} byte budget`);
  }
  return files;
}

describe("built images", () => {
  for (const site of [dist, draftsDist]) {
    it(`${site.dir.endsWith("dist-drafts") ? "drafts" : "production"}: every referenced image exists and stays under the CDN budget`, () => {
      assertImagesResolve(site);
    });
  }

  it("the home page eagerly loads only the loader art and the first frame", () => {
    for (const page of ["index.html", "en/index.html"]) {
      const html = dist.read(page);
      const preloads = [...html.matchAll(/<link rel="preload" as="image" href="([^"]+)"/g)].map((match) => match[1]);
      assert.equal(preloads.length, 1, page);
      const preloadFile = resolve(dist.dir, preloads[0].replace(/^\//, ""));
      const images = imgTagsOf(html);
      const firstScreen = images.filter((tag) => tag.includes("data-first-screen"));
      assert.equal(firstScreen.length, 2, `${page} first screen should be the scene and the first face`);
      assert.ok(firstScreen.every((tag) => !/\ssrc="/.test(tag)), page);
      const urls = [preloads[0], ...firstScreen.map((tag) => tag.match(/\bdata-src="([^"]+)"/)?.[1])];
      let bytes = 0;
      for (const url of urls) {
        assert.ok(url, page);
        const size = statSync(resolve(dist.dir, url.replace(/^\//, ""))).size;
        bytes += size;
      }
      assert.ok(statSync(preloadFile).size <= 120 * 1024, `${page} loader art is ${statSync(preloadFile).size} bytes`);
      assert.ok(bytes <= FIRST_SCREEN_BYTE_BUDGET, `${page} first screen is ${bytes} bytes`);
      assert.equal(html.match(/<video\b/g)?.length ?? 0, 0, page);

      const showcase = html.slice(html.indexOf('class="site-showcase"'), html.indexOf("</main>"));
      const lazy = imgTagsOf(showcase);
      assert.ok(lazy.length > 0, page);
      for (const tag of lazy) assert.match(tag, /\bloading="lazy"/, tag);

      const sprites = images.filter((tag) => tag.includes("data-expression"));
      assert.ok(sprites.length > 1, page);
      assert.equal(sprites.filter((tag) => tag.includes("data-first-screen")).length, 1, page);
      assert.ok(sprites.every((tag) => !/\ssrc="/.test(tag)), `${page} a later face is in the first response`);

      const firstCg = NARRATIVE_LINES[0]?.cg;
      const cgsWithSrc = images.filter((tag) => tag.includes("data-cg") && /\ssrc="/.test(tag));
      assert.equal(cgsWithSrc.length, firstCg ? 1 : 0, page);
    }
  });
});
