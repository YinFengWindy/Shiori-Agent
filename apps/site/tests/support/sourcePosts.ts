import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * The blog posts as written (src/content/blog and blog-en, #807), read
 * straight from their sources, for the tests that check the built site
 * against them.
 */

export const contentDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "src", "content");

/** A post as written: its slug, frontmatter fields and how many `##` sections it has. */
export interface SourcePost {
  readonly slug: string;
  readonly title: string;
  readonly description: string;
  readonly date: string;
  readonly draft: boolean;
  readonly sections: number;
}

/** The posts of one language as written, read straight from their frontmatter (values may be quoted). */
export function sourcePosts(dir: "blog" | "blog-en"): SourcePost[] {
  return readdirSync(resolve(contentDir, dir))
    .filter((file) => file.endsWith(".mdx"))
    .map((file) => {
      const text = readFileSync(resolve(contentDir, dir, file), "utf8").replaceAll("\r\n", "\n");
      const [, frontmatter = "", body = ""] = text.match(/^---\n(.*?)\n---\n(.*)$/s) ?? [];
      const field = (key: string) => {
        const value = frontmatter.match(new RegExp(`^${key}: (.+)$`, "m"))?.[1];
        assert.ok(value, `${dir}/${file} has no ${key}`);
        return value.replace(/^"(.*)"$/, "$1");
      };
      return {
        slug: file.replace(/\.mdx$/, ""),
        title: field("title"),
        description: field("description"),
        date: field("date"),
        draft: /^draft: true$/m.test(frontmatter),
        sections: body.split("\n").filter((line) => line.startsWith("## ")).length,
      };
    });
}

/** The published posts of one language as written. */
export function publishedPosts(dir: "blog" | "blog-en"): SourcePost[] {
  return sourcePosts(dir).filter((post) => !post.draft);
}

/**
 * The published Chinese posts without an English version. None may be left
 * once every post is translated: tests of how such a post is built then
 * have nothing to check, and skip.
 */
export function untranslatedPosts(): SourcePost[] {
  const translated = new Set(publishedPosts("blog-en").map((post) => post.slug));
  return publishedPosts("blog").filter((post) => !translated.has(post.slug));
}
