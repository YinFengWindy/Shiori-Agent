import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

/**
 * The blog (#773): one MDX file per post in `src/content/blog/`, its file
 * name (without `.mdx`) the post's slug, `/blog/<slug>/`. The frontmatter is
 * validated at build time, so a post missing its title, description or date
 * fails the build instead of shipping a broken page.
 *
 * A post marked `draft: true` is left out of every published page — the
 * list, the post page itself, the RSS feed and so the sitemap — unless the
 * site runs in drafts mode (`lib/blog.ts`).
 */
const blog = defineCollection({
  loader: glob({ pattern: "*.mdx", base: "./src/content/blog" }),
  schema: ({ image }) =>
    z.object({
      title: z.string().min(1),
      /** One or two sentences: the card summary, meta / OG description and RSS description. */
      description: z.string().min(1),
      /** Publication day (`YYYY-MM-DD`). */
      date: z.coerce.date(),
      /**
       * Picture on the list card and over the post, with its alt text: a
       * landscape gallery preview (`assets/gallery/`, 480px tall) suits it;
       * the portrait ones are too narrow for the reading column.
       */
      cover: z.object({ image: image(), alt: z.string().min(1) }).optional(),
      draft: z.boolean().default(false),
    }),
});

export const collections = { blog };
