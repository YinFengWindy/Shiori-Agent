import type { APIRoute } from "astro";
import { blogFeed } from "../../lib/blogFeed";

/** The blog's feed in English, `/en/rss.xml`: the translated posts (#807; lib/blogFeed.ts). */
export const GET: APIRoute = async ({ site }) => {
  if (!site) throw new Error("astro.config.ts must set `site`: the feed's links are built from it");
  return blogFeed("en", site);
};
