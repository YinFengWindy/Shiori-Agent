import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { defineHastPlugin, markdownToHtml } from "satteri";

/*
 * The changelog page (#792): the GitHub releases, fetched at build time and
 * rendered to static HTML. Fetching, filtering and the notes' clean-up are
 * plain functions here, unit-tested on fixture releases (tests/changelog.test.ts)
 * without a network request; `loadChangelog` wires them to the environment.
 */

/** The repository whose releases make the changelog. */
export const CHANGELOG_REPOSITORY = "YinFengWindy/Shiori-Agent";

/** The fields the changelog reads from one GitHub REST API release. */
export interface GitHubRelease {
  tag_name: string;
  name: string | null;
  body: string | null;
  draft: boolean;
  prerelease: boolean;
  /** `null` while a release is a draft. */
  published_at: string | null;
  html_url: string;
}

/** One version on the changelog page. */
export interface ChangelogEntry {
  /** The release's tag, e.g. `v0.5.2`: the version's heading and anchor. */
  version: string;
  publishedAt: Date;
  /** The release's page on GitHub. */
  url: string;
  /** The release notes as HTML, cleaned up (`releaseNotesMarkdown`). */
  html: string;
}

/** `fetch`, injectable so tests never touch the network. */
export type Fetch = (url: string, init: { headers: Record<string, string> }) => Promise<Response>;

/** The GitHub API's largest page. */
const PAGE_SIZE = 100;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Checks one release from the API (or a fixture) and keeps the fields the changelog reads. */
function parseRelease(value: unknown, at: string): GitHubRelease {
  if (!isRecord(value)) throw new Error(`${at}: a release must be an object`);
  const text = (key: string) => {
    const field = value[key];
    if (typeof field !== "string") throw new Error(`${at}: \`${key}\` must be a string`);
    return field;
  };
  const optionalText = (key: string) => (value[key] === null ? null : text(key));
  const flag = (key: string) => {
    const field = value[key];
    if (typeof field !== "boolean") throw new Error(`${at}: \`${key}\` must be a boolean`);
    return field;
  };
  return {
    tag_name: text("tag_name"),
    name: optionalText("name"),
    body: optionalText("body"),
    draft: flag("draft"),
    prerelease: flag("prerelease"),
    published_at: optionalText("published_at"),
    html_url: text("html_url"),
  };
}

/** Checks a list of releases as the API returns it. */
export function parseReleases(value: unknown, source: string): GitHubRelease[] {
  if (!Array.isArray(value)) throw new Error(`${source}: expected an array of releases`);
  return value.map((release, index) => parseRelease(release, `${source}[${index}]`));
}

/**
 * Every release of the repository, page by page, from the GitHub REST API.
 * With a token the requests are authenticated (5,000 an hour); without one
 * they are anonymous (60 an hour per address). Any failed request — network,
 * non-2xx, rate limit — throws: the changelog is never built from partial data.
 */
export async function fetchReleases(options: { token: string | undefined; fetch: Fetch }): Promise<GitHubRelease[]> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "shiori-site-build",
  };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;
  const releases: GitHubRelease[] = [];
  for (let page = 1; ; page += 1) {
    const url = `https://api.github.com/repos/${CHANGELOG_REPOSITORY}/releases?per_page=${PAGE_SIZE}&page=${page}`;
    const response = await options.fetch(url, { headers });
    if (!response.ok) {
      // GitHub's error body is a short JSON message (e.g. the rate limit); never the request's token.
      const detail = (await response.text()).slice(0, 300);
      throw new Error(`GitHub releases request failed: ${response.status} ${response.statusText} for ${url}: ${detail}`);
    }
    const batch = parseReleases(await response.json(), url);
    releases.push(...batch);
    if (batch.length < PAGE_SIZE) return releases;
  }
}

/**
 * The releases the changelog shows, newest first: published ones only.
 * Drafts are unpublished; prereleases are left out too, since the app's
 * updater and the download links only offer full releases.
 */
export function publishedReleases(releases: readonly GitHubRelease[]): (GitHubRelease & { published_at: string })[] {
  return releases
    .filter((release): release is GitHubRelease & { published_at: string } => !release.draft && !release.prerelease && release.published_at !== null)
    .sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
}

const ATX_HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;

/** Whether `line` opens or closes a fenced code block (headings inside one are code). */
function fenceMarker(line: string): string | undefined {
  return line.match(FENCE)?.[1];
}

/**
 * A release's notes, cleaned up for the page:
 * - HTML comments (machine-readable release metadata) go;
 * - a first-line `# …` heading naming the version (`# Shiori v0.5.2` over
 *   v0.5.2) goes, as the page already heads the notes with the version;
 * - the 「下载」 section goes — its heading and everything up to the next
 *   heading of the same or a higher level, or the end — since the page is
 *   not where the installer is offered.
 */
export function releaseNotesMarkdown(release: Pick<GitHubRelease, "tag_name" | "name" | "body">): string {
  const text = (release.body ?? "").replaceAll("\r\n", "\n").replace(/<!--[\s\S]*?-->/g, "");
  const lines = text.split("\n");

  const first = lines.findIndex((line) => line.trim() !== "");
  const title = first >= 0 ? lines[first].match(ATX_HEADING) : null;
  if (title && title[1] === "#") {
    const heading = (title[2] ?? "").trim();
    if (heading.includes(release.tag_name) || heading === release.name?.trim()) lines.splice(first, 1);
  }

  const kept: string[] = [];
  let fence: string | undefined;
  /** Level of the 下载 heading being skipped, while inside its section. */
  let skipping: number | undefined;
  for (const line of lines) {
    const marker = fenceMarker(line);
    if (fence === undefined) {
      const heading = line.match(ATX_HEADING);
      if (heading) {
        const level = heading[1].length;
        if (skipping !== undefined && level <= skipping) skipping = undefined;
        if (skipping === undefined && (heading[2] ?? "").trim() === "下载") skipping = level;
      }
      if (marker) fence = marker;
    } else if (marker && marker[0] === fence[0] && marker.length >= fence.length) {
      fence = undefined;
    }
    if (skipping === undefined) kept.push(line);
  }
  return kept.join("\n").trim();
}

/**
 * The notes' HTML fits under the page's headings: the page is the `h1`, each
 * version an `h2`, so the notes' headings start at `h3` (`#` and `##` both
 * become `h3`, deeper ones move down one level). Links off the site get
 * `rel="noopener"`.
 */
const releaseNotesPlugin = defineHastPlugin({
  name: "shiori-release-notes",
  element: [
    {
      filter: ["h1", "h2", "h3", "h4", "h5", "h6"],
      visit(node) {
        const level = Number(node.tagName.slice(1));
        return { ...node, tagName: `h${Math.min(6, Math.max(3, level + 1))}` };
      },
    },
    {
      filter: ["a"],
      visit(node, ctx) {
        const href = node.properties.href;
        if (typeof href === "string" && /^https?:\/\//i.test(href)) ctx.setProperty(node, "rel", ["noopener"]);
      },
    },
  ],
});

/** Release notes Markdown (GitHub-flavoured) as the page's HTML. */
export function renderReleaseNotes(markdown: string): string {
  return markdownToHtml(markdown, { hastPlugins: [releaseNotesPlugin] }).html;
}

// Releases carry a moment; readers are in China, so their day is read in Beijing time.
const releaseDateFormat = new Intl.DateTimeFormat("zh-CN", { dateStyle: "long", timeZone: "Asia/Shanghai" });

/** A release's day as readers see it (Beijing time), e.g. `2026年10月10日`. */
export function formatReleaseDate(date: Date): string {
  return releaseDateFormat.format(date);
}

/** Published releases, newest first, as changelog entries. */
export function changelogEntries(releases: readonly GitHubRelease[]): ChangelogEntry[] {
  return publishedReleases(releases).map((release) => ({
    version: release.tag_name,
    publishedAt: new Date(release.published_at),
    url: release.html_url,
    html: renderReleaseNotes(releaseNotesMarkdown(release)),
  }));
}

/** The build's environment, as far as the changelog reads it. */
export interface ChangelogEnv {
  /** Read-only GitHub token (Vercel: a fine-grained token; GitHub Actions: `github.token`). */
  GITHUB_TOKEN?: string;
  /**
   * Tests only: a JSON file of releases in the API's shape, read instead of
   * the API (relative to the working directory), so `site:test` builds offline
   * from known data (tests/fixtures/changelog.env).
   */
  SHIORI_SITE_RELEASES_FIXTURE?: string;
  /** Set on Vercel (`VERCEL=1`) and in CI (`CI`): a token is then required. */
  VERCEL?: string;
  CI?: string;
}

/**
 * The releases for this build: the fixture when one is named, otherwise the
 * GitHub API. Deployments and CI must authenticate — an anonymous request
 * there would share a rate limit with every other build on the machine — so
 * a missing token fails the build; local builds may go anonymous.
 */
export async function loadReleases(env: ChangelogEnv, fetch: Fetch): Promise<GitHubRelease[]> {
  const fixture = env.SHIORI_SITE_RELEASES_FIXTURE;
  if (fixture) {
    const path = resolve(fixture);
    return parseReleases(JSON.parse(await readFile(path, "utf8")), path);
  }
  const token = env.GITHUB_TOKEN || undefined;
  if (!token && (env.VERCEL || env.CI)) {
    throw new Error("GITHUB_TOKEN is not set: the changelog's GitHub releases request must be authenticated on Vercel and in CI");
  }
  return fetchReleases({ token, fetch });
}

let loaded: Promise<ChangelogEntry[]> | undefined;

/**
 * The changelog entries of this build, from `process.env`. Fetched once per
 * process, so `astro dev` reloads stay under the rate limit; a failure is
 * not kept, the next load tries again. No published release at all fails too:
 * the page is never built empty.
 */
export function loadChangelog(): Promise<ChangelogEntry[]> {
  loaded ??= loadReleases(process.env, fetch)
    .then((releases) => {
      const entries = changelogEntries(releases);
      if (entries.length === 0) throw new Error(`no published release of ${CHANGELOG_REPOSITORY}: the changelog would be empty`);
      return entries;
    })
    .catch((error: unknown) => {
      loaded = undefined;
      throw error;
    });
  return loaded;
}
