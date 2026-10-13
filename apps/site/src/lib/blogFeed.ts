import rss from "@astrojs/rss";
import { siteText } from "../i18n";
import { LOCALE_INFO, type Locale, localePath } from "../i18n/locales";
import { blogPostPath, getPublishedPosts } from "./blog";
import { SITE_NAME } from "./siteMeta";

/** Site path of the blog's feed in `locale`: `/rss.xml`, `/en/rss.xml`. */
export function blogFeedPath(locale: Locale): string {
  return localePath(locale, "/rss.xml");
}

/**
 * The blog's RSS feed in `locale` (#773, #807): every post published in it,
 * newest first, with its title, summary, day, byline and absolute link on
 * the canonical origin (`site`).
 */
export async function blogFeed(locale: Locale, site: URL): Promise<Response> {
  const text = siteText(locale).blog;
  const posts = await getPublishedPosts(locale);
  return rss({
    title: `${SITE_NAME} ${text.title}`,
    description: text.description,
    // The channel's link: the list page; item links resolve against it.
    site: new URL(localePath(locale, "/blog/"), site),
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.date,
      link: blogPostPath(post.id, locale),
      // RSS <author> must be an e-mail address; the byline goes in dc:creator.
      customData: `<dc:creator>${text.author}</dc:creator>`,
    })),
    xmlns: { dc: "http://purl.org/dc/elements/1.1/" },
    customData: `<language>${LOCALE_INFO[locale].htmlLang}</language>`,
  });
}
