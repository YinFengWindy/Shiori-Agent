import rss from "@astrojs/rss";
import type { APIRoute } from "astro";
import { BLOG_AUTHOR, BLOG_DESCRIPTION, BLOG_TITLE, blogPostPath, getPublishedPosts } from "../lib/blog";
import { SITE_NAME } from "../lib/siteMeta";

/**
 * The blog's RSS feed (#773): every published post, newest first, with its
 * title, summary, day, byline and absolute link on the canonical origin
 * (`site`).
 */
export const GET: APIRoute = async ({ site }) => {
  if (!site) throw new Error("astro.config.ts must set `site`: the feed's links are built from it");
  const posts = await getPublishedPosts();
  return rss({
    title: `${SITE_NAME} ${BLOG_TITLE}`,
    description: BLOG_DESCRIPTION,
    // The channel's link: the list page; item links resolve against it.
    site: new URL("/blog/", site),
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.date,
      link: blogPostPath(post),
      // RSS <author> must be an e-mail address; the byline goes in dc:creator.
      customData: `<dc:creator>${BLOG_AUTHOR}</dc:creator>`,
    })),
    xmlns: { dc: "http://purl.org/dc/elements/1.1/" },
    customData: "<language>zh-CN</language>",
  });
};
