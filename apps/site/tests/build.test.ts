import assert from "node:assert/strict";
import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";
import { GALLERY_ARTS, GALLERY_THUMB_HEIGHT, GALLERY_THUMB_MAX_BYTES } from "../src/content/gallery";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { SHOWCASE_CLIP_IDS, SHOWCASE_STILL_MAX_BYTES } from "../src/content/showcase";
import { zh } from "../src/i18n/zh";
import {
  ORIGIN,
  assertDescription,
  breadcrumbsOf,
  dist as site,
  distPathOf,
  draftsDist,
  idsOf,
  imgTagsOf,
  isRecord,
  jsonLdOf,
  metaContent,
  pictureAt,
  sectionIndexOf,
  sitemapEntries,
  sitemapPages,
  topBarHomeHref,
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

  it("declares the language, and a title and description carrying the companion search words (#799)", () => {
    assert.match(html, /<html lang="zh-CN">/);
    assert.match(html, /<title>Shiori · 会慢慢喜欢上你的 AI 伴侣 · 开源免费的 Personal Agent<\/title>/);
    assertDescription(metaContent(html, "name", "description"), ["Shiori", "AI 伴侣", "AI 女友", "Personal Agent", "开源免费", "Windows"]);
  });

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

  it("describes the site, its publisher and the app as structured data, the app's version from the newest release (#799)", async () => {
    const [data, ...others] = jsonLdOf(html);
    assert.equal(others.length, 0, "the home page has one JSON-LD block");
    assert.ok(isRecord(data) && data["@context"] === "https://schema.org" && Array.isArray(data["@graph"]));
    const graph = data["@graph"].filter(isRecord);
    const byType = (type: string) => {
      const items = graph.filter((item) => item["@type"] === type);
      assert.equal(items.length, 1, `expected one ${type}`);
      return items[0];
    };
    const organization = byType("Organization");
    const website = byType("WebSite");
    const app = byType("SoftwareApplication");
    const publisher = { "@id": `${ORIGIN}/#organization` };
    assert.equal(organization["@id"], publisher["@id"]);
    assert.equal(organization.name, "Shiori");
    assert.equal(organization.url, `${ORIGIN}/`);
    assert.ok(isRecord(organization.logo) && typeof organization.logo.url === "string");
    assert.ok(site.has(distPathOf(organization.logo.url)), "the logo is not in the build output");
    assert.deepEqual(organization.sameAs, ["https://github.com/YinFengWindy/Shiori-Agent"]);
    assert.deepEqual(
      { name: website.name, url: website.url, inLanguage: website.inLanguage, publisher: website.publisher },
      { name: "Shiori", url: `${ORIGIN}/`, inLanguage: "zh-CN", publisher },
    );
    assert.deepEqual(
      { ...app, image: undefined },
      {
        "@type": "SoftwareApplication",
        "@id": `${ORIGIN}/#software`,
        name: "Shiori",
        description: metaContent(html, "name", "description"),
        url: `${ORIGIN}/`,
        image: undefined,
        operatingSystem: "Windows",
        applicationCategory: "LifestyleApplication",
        inLanguage: "zh-CN",
        isAccessibleForFree: true,
        offers: { "@type": "Offer", price: "0", priceCurrency: "CNY" },
        downloadUrl: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
        // The newest published full release of tests/fixtures/releases.json.
        softwareVersion: "0.5.3",
        dateModified: "2026-10-10T10:36:03.000Z",
        license: "https://github.com/YinFengWindy/Shiori-Agent/blob/main/LICENSE",
        author: publisher,
        publisher,
      },
    );
    assert.equal(app.image, metaContent(html, "property", "og:image"));
    assert.deepEqual(await pictureAt(site, String(app.image)), { format: "jpeg", width: 1200, height: 630 });
  });

  it("points canonical and og:url at the site root on the production origin", () => {
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/">`));
    assert.equal(metaContent(html, "property", "og:url"), `${ORIGIN}/`);
  });

  it("carries Open Graph and Twitter card tags with an absolute, emitted image", () => {
    assert.equal(metaContent(html, "property", "og:type"), "website");
    assert.equal(metaContent(html, "property", "og:title"), "Shiori · 会慢慢喜欢上你的 AI 伴侣 · 开源免费的 Personal Agent");
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
    for (const text of NARRATIVE_LINES.map((line) => zh.narrative.lines[line.id])) {
      const at = html.indexOf(`>${text}</p>`, from);
      assert.ok(at >= 0, `narrative line missing or out of order: ${text}`);
      from = at;
    }
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

  it("has no skip control", () => {
    assert.doesNotMatch(html, /跳过/);
  });

  it("paints with no external stylesheet: every CSS rule is inline", () => {
    assert.doesNotMatch(html, /<link [^>]*rel="stylesheet"/);
    assert.doesNotMatch(html, /@import/);
  });

  it("opens the body with the loader, hidden from the accessibility tree, before the page content", () => {
    const body = html.slice(html.indexOf("<body>") + "<body>".length);
    assert.match(body, /^<div id="site-loader" class="site-loader" aria-hidden="true"/);
    assert.ok(body.indexOf("site-loader-progress") < body.indexOf("<main>"), "the loader must come before <main>");
  });

  it("shows 吟风's illustration over the wash, preloaded from the head as the page's first picture", () => {
    const art = html.match(/<div id="site-loader"[^>]*><div class="site-loader-wash"><\/div><img class="site-loader-art" src="([^"]+)"[^>]*>/);
    assert.ok(art, "no illustration right after the loader's wash");
    const [tag, src] = art;
    assert.match(src, /^\/_astro\/cg-6\.[\w-]+\.webp$/);
    assert.ok(existsSync(resolve(dist, src.slice(1))), `${src} is not in the build output`);
    assert.match(tag, /fetchpriority="high"/);
    const head = html.slice(0, html.indexOf("</head>"));
    const preload = head.indexOf(`<link rel="preload" as="image" href="${src}" fetchpriority="high">`);
    assert.ok(preload >= 0, "the illustration is not preloaded from the head");
    assert.ok(preload < head.indexOf("<style>"), "the preload must come before the inlined stylesheet");
    assert.ok(head.indexOf("<img") < 0 && !head.slice(0, preload).includes('rel="preload"'), "it must be the first preload");
    // Crisp: no blurred inline placeholders any more.
    assert.doesNotMatch(html, /data:image\//);
  });

  it("drifts a few brand petals over the illustration, and holds 吟风 and the dialogue box back until the reveal", () => {
    const petals = html.match(/<div class="site-loader-petals">(.*?)<\/div>/s)?.[1] ?? "";
    assert.ok([...petals.matchAll(/<svg class="site-loader-petal"/g)].length >= 5);
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");
    assert.match(styles, /html\[data-site-loader=loading\] \.site-narrative-figure\{[^}]*opacity:0/);
    assert.match(styles, /html\[data-site-loader=loading\] \.site-dialogue\{[^}]*opacity:0/);
  });

  it("shows a progress line whose head carries a brand sparkle and the percentage, starting at 0%", () => {
    assert.match(
      html,
      /<div class="site-loader-progress"><div class="site-loader-track"><div class="site-loader-fill"><\/div><div class="site-loader-head"><svg class="site-loader-star" viewBox="4 4 16 16">.*?<\/svg><span [^>]*data-loader-percent[^>]*>0%<\/span><\/div><\/div><\/div>/s,
    );
  });

  it("leaves the first screen to the loader: no src on its pictures, a <noscript> copy for each one shown", () => {
    const sprites = [...html.matchAll(/<img [^>]*data-expression="[^"]+"[^>]*>/g)].map((match) => match[0]);
    assert.equal(sprites.length, 8);
    for (const sprite of sprites) {
      assert.match(sprite, /data-first-screen/);
      assert.match(sprite, / data-src="\/_astro\/yinfeng-/);
      assert.doesNotMatch(sprite, / src=/);
    }
    const backdrops = [...html.matchAll(/<img data-scene-backdrop data-first-screen[^>]*>/g)].map((match) => match[0]);
    assert.equal(backdrops.length, 1, "only the narrative's backdrop is first-screen");
    assert.doesNotMatch(backdrops[0], / src=/);
    const noscripts = [...html.matchAll(/<noscript><img src="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(noscripts.length, 2, "the backdrop and the first sprite need a no-script copy");
    assert.ok(noscripts.some((src) => src.includes("/bg-day.")) && noscripts.some((src) => src.includes("/yinfeng-")));
  });

  it("leaves every narrative CG but the first line's without src: each is fetched as its line draws near", () => {
    const cgs = [...html.matchAll(/<img [^>]*class="site-narrative-cg"[^>]*>/g)].map((match) => match[0]);
    assert.ok(cgs.length > 0);
    const firstCg = NARRATIVE_LINES[0]?.cg;
    for (const cg of cgs) {
      const key = cg.match(/ data-cg="([^"]+)"/)?.[1];
      assert.ok(key, `CG without data-cg: ${cg}`);
      assert.match(cg, / data-src="\/_astro\/[^"]+"/);
      if (key === firstCg) assert.match(cg, /^<img src="/);
      else assert.doesNotMatch(cg, / src=/, `${key} must not download up front`);
    }
  });

  it("has no video: nothing streams in behind the pictures", () => {
    assert.doesNotMatch(html, /<video[\s>]|<source /);
  });

  it("knows the exact byte size of every picture the first screen may wait for", () => {
    const attribute = html.match(/<div id="site-loader"[^>]* data-bytes="([^"]+)"/)?.[1];
    assert.ok(attribute, "no data-bytes on the loader");
    const sizes: Record<string, number> = JSON.parse(attribute.replaceAll("&quot;", '"'));
    const urls = [...html.matchAll(/<img [^>]*data-first-screen[^>]*>/g)].flatMap((match) => {
      const tag = match[0];
      return [tag.match(/ data-src="([^"]+)"/)?.[1], tag.match(/ data-dusk="([^"]+)"/)?.[1], tag.match(/ data-night="([^"]+)"/)?.[1]];
    }).filter((url): url is string => Boolean(url));
    assert.equal(urls.length, 8 + 3);
    for (const url of urls) {
      assert.equal(sizes[url], statSync(resolve(dist, url.slice(1))).size, `size of ${url}`);
    }
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
    assert.match(styles, /@media \(scripting:none\)\{\.site-loader,img\[data-first-screen\]\{display:none\}\}/);
    assert.match(styles, /\.site-loader-percent\{[^}]*font-variant-numeric:tabular-nums/);
    // Reduced motion: the bar jumps in steps and no loop runs (no sweep, twinkle, flash or falling petals).
    const reduced = styles.match(/@media \(prefers-reduced-motion:reduce\),\(scripting:none\)\{(.*?)\}\}/s)?.[1] ?? "";
    assert.match(reduced, /\.site-loader-fill,\.site-loader-head\{transition:none\}/);
    assert.match(reduced, /\.site-loader-fill:after,\.site-loader-petals\{display:none\}/);
    assert.match(reduced, /\.site-loader-star,\.site-loader\[data-leaving\] \.site-loader-star\{animation:none\}/);
  });

  it("drives the loader from an inline script, not a bundle that may still be downloading", () => {
    const script = html.match(/<div id="site-loader".*?<script>(.*?)<\/script>/s)?.[1];
    assert.ok(script, "no inline <script> follows the loader");
    assert.match(script, /img\[data-first-screen\]\[data-src\]/);
    assert.match(script, /response\.body\.getReader\(\)/);
    assert.match(script, /--site-loader-progress/);
    assert.match(script, /--site-loader-cap/);
    assert.match(script, /data-leaving/);
    // The narrative's CGs load as their lines draw near (NarrativeStage.astro), not after the loader.
    assert.doesNotMatch(script, /data-cg/);
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

  describe("showcase after the narrative (#772)", () => {
    const start = html.indexOf('<section class="site-showcase"');
    const end = html.indexOf("</section>", html.indexOf('class="site-photostrip"'));
    const showcase = html.slice(start, end);

    it("follows the download call, inside the free-scrolling block after the narrative", () => {
      assert.ok(start > html.indexOf('id="download"'), "the showcase must come after the download call");
      assert.ok(start > html.indexOf('class="site-after-narrative"'), "the showcase belongs in .site-after-narrative");
    });

    it("carries every feature title and line as static text, in order", () => {
      let from = 0;
      for (const feature of SHOWCASE_FEATURES) {
        const title = showcase.indexOf(`<h2 class="site-feature-title site-story-type">${feature.title}</h2>`, from);
        assert.ok(title >= 0, `feature title missing or out of order: ${feature.title}`);
        assert.ok(showcase.indexOf(`>${feature.line}</p>`, title) >= 0, `feature line missing: ${feature.line}`);
        from = title;
      }
    });

    it("shows every feature's still: an emitted WebP within budget, alt text, intrinsic size, lazy", () => {
      // One block per clip, in the clips' order.
      assert.deepEqual(SHOWCASE_FEATURES.map((feature) => feature.clip), [...SHOWCASE_CLIP_IDS]);
      const blocks = [...showcase.matchAll(/<article id="([^"]+)" class="site-feature">(.*?)<\/article>/gs)];
      assert.deepEqual(blocks.map((block) => block[1]), [...SHOWCASE_CLIP_IDS]);
      for (const [index, [, , block]] of blocks.entries()) {
        const feature = SHOWCASE_FEATURES[index];
        const images = [...block.matchAll(/<img [^>]*>/g)].map((match) => match[0]);
        assert.equal(images.length, 1, `${feature.clip} block needs exactly one picture`);
        const [image] = images;
        assert.ok(image.includes(` alt="${feature.stillAlt}"`), `${feature.clip} still has no alt text`);
        for (const attribute of [/ loading="lazy"/, / decoding="async"/, / width="\d+"/, / height="\d+"/]) {
          assert.match(image, attribute);
        }
        const src = image.match(/ src="([^"]+)"/)?.[1];
        assert.ok(src, `${feature.clip} still has no src`);
        assert.ok(src.startsWith(`/_astro/${feature.clip}.`) && src.endsWith(".webp"), `${feature.clip} still is ${src}`);
        const size = statSync(resolve(dist, src.slice(1))).size;
        assert.ok(size <= SHOWCASE_STILL_MAX_BYTES, `${src} is ${size} bytes, over the ${SHOWCASE_STILL_MAX_BYTES}-byte budget`);
      }
    });

    it("shows the photo strip as plain, lazy pictures with alt text, nothing clickable, the loop copy hidden", () => {
      const strip = showcase.slice(showcase.indexOf('class="site-photostrip"'));
      assert.doesNotMatch(strip, /<a |<button/);
      const prints = [...strip.matchAll(/<li class="site-photo"([^>]*)><img ([^>]*)><\/li>/g)].map(([, item, img]) => ({
        hidden: item.includes('aria-hidden="true"'),
        lazy: / loading="lazy"/.test(img),
        alt: img.match(/ alt="([^"]*)"/)?.[1],
        src: img.match(/ src="([^"]+)"/)?.[1],
      }));
      assert.ok(prints.length > 0 && prints.length % 2 === 0, "the row is listed twice for a seamless loop");
      const row = prints.slice(0, prints.length / 2);
      const copy = prints.slice(prints.length / 2);
      assert.ok(prints.every((print) => print.lazy), "every print loads lazily");
      for (const print of row) {
        assert.ok(!print.hidden && print.alt?.startsWith("CG："), `print ${print.src} needs alt text`);
      }
      assert.deepEqual(copy.map((print) => print.src), row.map((print) => print.src));
      assert.ok(copy.every((print) => print.hidden && print.alt === ""), "the loop copy is hidden from assistive tech");
    });

    it("prints small previews, not the full-size art: one per strip entry, 2× the print height, each within budget", () => {
      const strip = showcase.slice(showcase.indexOf('class="site-photostrip"'));
      const tags = [...strip.matchAll(/<li class="site-photo"[^>]*>(<img [^>]*>)/g)].map((match) => match[1]);
      const row = tags.slice(0, tags.length / 2);
      assert.equal(row.length, GALLERY_ARTS.length);
      for (const [index, tag] of row.entries()) {
        const art = GALLERY_ARTS[index];
        const src = tag.match(/ src="([^"]+)"/)?.[1];
        assert.ok(src, `print ${index} has no src`);
        assert.ok(src.startsWith(`/_astro/${art}.`) && src.endsWith(".webp"), `print ${index} is ${src}`);
        assert.match(tag, new RegExp(` height="${GALLERY_THUMB_HEIGHT}"`));
        const size = statSync(resolve(dist, src.slice(1))).size;
        assert.ok(size <= GALLERY_THUMB_MAX_BYTES, `${src} is ${size} bytes, over the ${GALLERY_THUMB_MAX_BYTES}-byte budget`);
      }
    });
  });

  it("ends with a footer linking GitHub, the releases and the MIT license, with the copyright year", () => {
    const footer = html.match(/<footer class="site-footer">(.*?)<\/footer>/s)?.[1];
    assert.ok(footer, "no footer");
    assert.ok(html.indexOf("<footer") > html.indexOf("</main>"), "the footer follows the main content");
    assert.match(footer, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent"[^>]*>.*?GitHub<\/a>/s);
    assert.match(footer, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases"[^>]*>.*?Release<\/a>/s);
    assert.match(footer, /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/blob\/main\/LICENSE"[^>]*>.*?MIT 许可<\/a>/s);
    assert.match(footer, /© \d{4} Shiori/);
  });

  describe("top bar (#773)", () => {
    const bar = html.match(/<header class="site-header" data-site-header data-mode="reveal">(.*?)<\/header>/s);
    const styles = [...html.matchAll(/<style>(.*?)<\/style>/gs)].map((match) => match[1]).join("\n");

    it("sits after the loader and outside the narrative, so the stage's stepping never sees it", () => {
      assert.ok(bar, "no reveal-mode top bar");
      const at = html.indexOf(bar[0]);
      assert.ok(at > html.indexOf('id="site-loader"'), "the loader must open the body");
      assert.ok(at < html.indexOf("<main>"), "the bar comes before the page content, outside the narrative stage");
    });

    it("links the icon and name to the narrative's download state, then 博客, 更新日志, GitHub, the English home page and the Windows download", () => {
      assert.ok(bar);
      const links = [...bar[1].matchAll(/<a href="([^"]+)"[^>]*>(.*?)<\/a>/gs)].map(([, href, label]) => ({
        href,
        label: label.replace(/<[^>]+>/g, ""),
      }));
      assert.deepEqual(links, [
        { href: "/#download", label: "Shiori" },
        { href: "/blog/", label: "博客" },
        { href: "/changelog/", label: "更新日志" },
        { href: "https://github.com/YinFengWindy/Shiori-Agent", label: "GitHub" },
        { href: "/en/", label: "EN" },
        { href: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest", label: "下载 Windows 版" },
      ]);
      assert.match(bar[1], /<img src="\/icons\/icon-192\.png"[^>]* alt=""/);
      // The link's target is the download call the narrative ends on.
      assert.match(html, /<div id="download" class="site-download" data-narrative-download>/);
      assert.match(bar[1], /<a href="https:\/\/github\.com\/YinFengWindy\/Shiori-Agent\/releases\/latest"[^>]* data-download-installer>/);
    });

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
    const pages = sitemapPages(site);
    assert.ok(pages.includes(`${ORIGIN}/`), `home page missing from sitemap: ${pages.join(", ")}`);
    for (const page of pages) distPathOf(page);
  });

  it("dates every sitemap page by the update time it states, never the build's clock (#799)", () => {
    const entries = sitemapEntries(site);
    for (const { loc, lastmod } of entries) {
      assert.ok(lastmod, `${loc} has no lastmod`);
      assert.equal(lastmod, new Date(metaContent(site.read(distPathOf(loc)), "property", "og:updated_time")).toISOString(), `${loc}'s lastmod is not its page's`);
    }
    const lastmodOf = (url: string) => entries.find((entry) => entry.loc === url)?.lastmod ?? "";
    // The newest published release of tests/fixtures/releases.json.
    assert.equal(lastmodOf(`${ORIGIN}/changelog/`), "2026-10-10T10:36:03.000Z");
    // The blog list: its newest post. The home page: the newer of that and the newest release.
    const posts = entries.filter((entry) => /\/blog\/[^/]+\/$/.test(entry.loc)).map((entry) => entry.lastmod ?? "");
    const newestPost = posts.reduce((newest, day) => (day > newest ? day : newest), "");
    assert.equal(lastmodOf(`${ORIGIN}/blog/`), newestPost);
    assert.equal(lastmodOf(`${ORIGIN}/`), [newestPost, lastmodOf(`${ORIGIN}/changelog/`)].sort().at(-1));
  });
});

/*
 * The search engines' verification tags (#799): the drafts-mode test build
 * runs with tests/fixtures/site-verification.env, the production-mode one
 * without it.
 */
describe("site verification tags", () => {
  const tags = (html: string) => [...html.matchAll(/<meta name="(google-site-verification|msvalidate\.01|baidu-site-verification)" content="([^"]*)">/g)].map(([, name, content]) => ({ name, content }));

  it("names each engine's token when the build has it, on every page", () => {
    for (const page of ["index.html", "blog/index.html", "changelog/index.html"]) {
      assert.deepEqual(tags(draftsDist.read(page)), [
        { name: "google-site-verification", content: "test-google-token" },
        { name: "msvalidate.01", content: "TEST-BING-TOKEN" },
        { name: "baidu-site-verification", content: "codeva-test-baidu" },
      ]);
    }
  });

  it("writes none when the build has no tokens", () => {
    for (const page of ["index.html", "blog/index.html", "changelog/index.html"]) assert.deepEqual(tags(readDist(page)), []);
  });
});

/*
 * The changelog page as `site:test` builds it: from tests/fixtures/releases.json
 * (tests/fixtures/changelog.env), so the expected releases are known here.
 * The notes' clean-up itself is unit-tested in changelog.test.ts.
 */
describe("changelog page (#792)", () => {
  const html = readDist("changelog/index.html");
  const changelogUrl = `${ORIGIN}/changelog/`;

  it("carries its own title and description, with the companion search words, canonical URL and Open Graph tags", () => {
    assert.match(html, /<title>更新日志 · Shiori AI 伴侣<\/title>/);
    assertDescription(metaContent(html, "name", "description"), ["Shiori", "AI 伴侣", "Personal Agent", "开源免费", "Windows"]);
    assert.match(html, new RegExp(`<link rel="canonical" href="${changelogUrl}">`));
    assert.equal(metaContent(html, "property", "og:url"), changelogUrl);
    assert.equal(metaContent(html, "property", "og:type"), "website");
    assert.equal(metaContent(html, "property", "og:title"), "更新日志 · Shiori AI 伴侣");
  });

  it("is in the sitemap", () => {
    assert.ok(sitemapPages(site).includes(changelogUrl));
  });

  it("marks 更新日志 current in the always-there top bar, linked from every page", () => {
    assert.match(html, /<header class="site-header" data-site-header data-mode="fixed">/);
    assert.match(html, /<a href="\/changelog\/"[^>]* aria-current="page">更新日志<\/a>/);
    for (const page of ["index.html", "blog/index.html"]) assert.match(readDist(page), /<a href="\/changelog\/"[^>]*>更新日志<\/a>/);
  });

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

  it("leads back home with a 首页 / 更新日志 breadcrumb and BreadcrumbList data; the icon and name go to the download state", () => {
    const { steps, jsonLd } = breadcrumbsOf(html);
    assert.deepEqual(steps, [
      { label: "首页", href: "/#download", current: false },
      { label: "更新日志", href: undefined, current: true },
    ]);
    assert.deepEqual(jsonLd, {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "首页", item: `${ORIGIN}/` },
        { "@type": "ListItem", position: 2, name: "更新日志", item: changelogUrl },
      ],
    });
    assert.equal(topBarHomeHref(html), "/#download");
  });

  it("indexes every version with its day, linked to its release, beside the list and folded for narrow screens", () => {
    const { aside, inline } = sectionIndexOf(html);
    assert.ok(aside, "no sticky version index");
    assert.ok(inline, "no folded <details> version index");
    assert.equal(aside.title, "版本");
    assert.equal(aside.label, "版本");
    assert.equal(inline.title, "版本");
    assert.deepEqual(inline.entries, aside.entries);
    assert.deepEqual(aside.entries, [
      { id: "v0.5.3", label: "v0.5.3", note: "2026年10月10日", level: 0 },
      { id: "v0.5.2", label: "v0.5.2", note: "2026年10月10日", level: 0 },
      { id: "v0.1.0", label: "v0.1.0", note: "2026年8月23日", level: 0 },
    ]);
    // Each anchor is the release's own element, and the index covers every release on the page.
    assert.deepEqual(
      aside.entries.map((entry) => entry.id),
      idsOf(html, "article"),
    );
  });

  it("marks the notes' links off the site rel=noopener", () => {
    const notes = html.slice(html.indexOf('<div class="site-prose">'), html.indexOf("</main>"));
    const links = [...notes.matchAll(/<a href="(https?:[^"]+)"([^>]*)>/g)].filter(([, href]) => !href.startsWith(ORIGIN));
    assert.ok(links.length > 0);
    for (const [, href, rest] of links) assert.match(rest, /rel="noopener"/, `${href} has no rel=noopener`);
  });
});
