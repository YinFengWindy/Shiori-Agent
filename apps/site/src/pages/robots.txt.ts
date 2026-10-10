import type { APIRoute } from "astro";

/**
 * robots.txt, generated at build time so the sitemap URL follows `site` in
 * astro.config.ts. The sitemap itself is written by `@astrojs/sitemap`.
 */
export const GET: APIRoute = ({ site }) => {
  if (!site) throw new Error("astro.config.ts must set `site`: robots.txt points at the absolute sitemap URL");
  const sitemapUrl = new URL("sitemap-index.xml", site).href;
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${sitemapUrl}\n`, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
