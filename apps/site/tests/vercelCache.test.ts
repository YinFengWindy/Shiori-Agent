import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

/**
 * Vercel reads `vercel.json` from the project Root Directory. This repo's
 * file sets `outputDirectory` to `apps/site/dist` and the build command to
 * the workspace script, so that directory is the repository root — a copy
 * under `apps/site/` would not be the one the deployment uses.
 *
 * Header rules all apply. For one header name, the last matching rule wins,
 * which is why the hashed `/_astro/` rule stays below the HTML catch-all.
 */
const vercelPath = fileURLToPath(new URL("../../../vercel.json", import.meta.url));
const siteVercelPath = fileURLToPath(new URL("../vercel.json", import.meta.url));

interface HeaderRule {
  source: string;
  headers: { key: string; value: string }[];
}

function sourceToRegExp(source: string): RegExp {
  let out = "";
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "(") {
      let depth = 0;
      let j = i;
      for (; j < source.length; j += 1) {
        if (source[j] === "(") depth += 1;
        else if (source[j] === ")") {
          depth -= 1;
          if (depth === 0) break;
        }
      }
      out += source.slice(i, j + 1);
      i = j;
    } else {
      out += /[.*+?^${}|[\]\\]/.test(ch) ? `\\${ch}` : ch;
    }
  }
  return new RegExp(`^${out}$`);
}

function cacheControl(rules: HeaderRule[], path: string): string | undefined {
  let value: string | undefined;
  for (const rule of rules) {
    if (!sourceToRegExp(rule.source).test(path)) continue;
    const header = rule.headers.find((item) => item.key.toLowerCase() === "cache-control");
    if (header) value = header.value;
  }
  return value;
}

describe("vercel cache headers", () => {
  const config = JSON.parse(readFileSync(vercelPath, "utf8")) as {
    outputDirectory?: string;
    headers?: HeaderRule[];
  };
  const rules = config.headers ?? [];

  it("is the root project config, not a second file under the site package", () => {
    assert.equal(config.outputDirectory, "apps/site/dist");
    assert.equal(existsSync(siteVercelPath), false);
  });

  it("keeps HTML revalidated and caches hashed /_astro assets for a year", () => {
    const html = "public, max-age=0, must-revalidate";
    const immutable = "public, max-age=31536000, immutable";
    for (const path of ["/", "/index.html", "/blog/", "/blog/a-post", "/en/", "/en/changelog", "/changelog/", "/robots.txt", "/rss.xml", "/en/rss.xml", "/sitemap-index.xml"]) {
      assert.equal(cacheControl(rules, path), html, path);
    }
    for (const path of ["/_astro/scene.abc123.webp", "/_astro/page.hash.css", "/_astro/hoisted.hash.js"]) {
      assert.equal(cacheControl(rules, path), immutable, path);
    }
    // The prefix is the directory, not a sibling path.
    assert.equal(cacheControl(rules, "/_astroevil"), html);
  });

  it("gives unhashed icons a day, not a year", () => {
    const day = "public, max-age=86400";
    for (const path of ["/favicon.ico", "/icons/favicon-32.png", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png"]) {
      assert.equal(cacheControl(rules, path), day, path);
    }
  });
});
