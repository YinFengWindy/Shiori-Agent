import assert from "node:assert/strict";
import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";
import { GALLERY_PHOTOS, GALLERY_THUMB_HEIGHT, GALLERY_THUMB_MAX_BYTES } from "../src/content/gallery";
import { NARRATIVE_LINES } from "../src/content/narrative";
import { SHOWCASE_CLIP_IDS, SHOWCASE_FEATURES, SHOWCASE_STILL_MAX_BYTES } from "../src/content/showcase";
import { ORIGIN, dist as site, distPathOf, metaContent, sitemapPages } from "./support/builtSite";

/*
 * Assertions on the built site (`astro build` runs first, see the package's
 * `test` script). Reading the emitted files directly is what a crawler that
 * does not execute JavaScript sees, so every check here holds without JS.
 * The blog's pages are covered by blog.test.ts.
 */

const dist = site.dir;
const readDist = site.read;

describe("home page HTML", () => {
  const html = readDist("index.html");

  it("declares the language and a non-empty title and description", () => {
    assert.match(html, /<html lang="zh-CN">/);
    assert.match(html, /<title>Shiori · 会慢慢喜欢上你的 AI 伴侣<\/title>/);
    assert.ok(metaContent(html, "name", "description").includes("AI 伴侣"));
  });

  it("points canonical and og:url at the site root on the production origin", () => {
    assert.match(html, new RegExp(`<link rel="canonical" href="${ORIGIN}/">`));
    assert.equal(metaContent(html, "property", "og:url"), `${ORIGIN}/`);
  });

  it("carries Open Graph and Twitter card tags with an absolute, emitted image", () => {
    assert.equal(metaContent(html, "property", "og:type"), "website");
    assert.equal(metaContent(html, "property", "og:title"), "Shiori · 会慢慢喜欢上你的 AI 伴侣");
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
        // An empty alt is emitted as a bare `alt`.
        alt: / alt( |$)/.test(img) ? "" : img.match(/ alt="([^"]*)"/)?.[1],
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
      assert.equal(row.length, GALLERY_PHOTOS.length);
      for (const [index, tag] of row.entries()) {
        const { art } = GALLERY_PHOTOS[index] ?? {};
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

    it("links the icon and name home, then 博客, 更新日志, GitHub and the Windows download — no in-page anchors", () => {
      assert.ok(bar);
      const links = [...bar[1].matchAll(/<a href="([^"]+)"[^>]*>(.*?)<\/a>/gs)].map(([, href, label]) => ({
        href,
        label: label.replace(/<[^>]+>/g, ""),
      }));
      assert.deepEqual(links, [
        { href: "/", label: "Shiori" },
        { href: "/blog/", label: "博客" },
        { href: "https://github.com/YinFengWindy/Shiori-Agent/releases", label: "更新日志" },
        { href: "https://github.com/YinFengWindy/Shiori-Agent", label: "GitHub" },
        { href: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest", label: "下载 Windows 版" },
      ]);
      assert.match(bar[1], /<img src="\/icons\/icon-192\.png"[^>]* alt=""/);
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
});
