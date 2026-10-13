// Second half of the Vercel ignore step (vercel-ignore-build.sh), run when
// the last commit changed nothing of the site: builds (exit 1) when a
// release may be missing from the changelog (/changelog/, #792), skips
// (exit 0) otherwise. Any failure to tell — network, rate limit, an
// unexpected answer — builds. Node built-ins only: the ignore step runs
// before dependencies install. The decision itself is `shouldBuild`, tested
// in tests/vercelReleaseSinceHead.test.ts.
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

/** The repository whose releases make the changelog; same as CHANGELOG_REPOSITORY in src/lib/changelog.ts. */
const REPOSITORY = "YinFengWindy/Shiori-Agent";

/**
 * How long after a release is published it still forces a build. The
 * release workflows call the Deploy Hook right after publishing
 * (.github/workflows/site-redeploy-on-release.yml), so the hook's build
 * starts within minutes; 30 minutes leaves room for a queued build.
 */
export const RECENT_RELEASE_MS = 30 * 60 * 1000;

/**
 * Whether this deployment must build, given the newest releases (the API's
 * first page) and the last commit's time. It builds when a published
 * release (drafts aside) either
 * - came out after the last commit: the site was last built without it; or
 * - came out less than RECENT_RELEASE_MS ago: the hook's build, even when a
 *   commit that touched nothing of the site landed between the release and
 *   the build, or when the release was not marked latest.
 * What is left: a hook build delayed past the window while a newer
 * non-site commit landed first is skipped. Vercel marks no deployment as
 * hook-made, so that cannot be told apart from an ordinary push; the next
 * release or site change rebuilds, or the owner redeploys by hand.
 *
 * @param {{ releases: { tag_name: string; draft: boolean; published_at: string | null }[]; committedAt: number; now: number }} input
 *   `committedAt` and `now` in milliseconds since the epoch.
 * @returns {{ build: boolean; reason: string }}
 */
export function shouldBuild({ releases, committedAt, now }) {
  for (const release of releases) {
    if (release.draft || release.published_at === null) continue;
    const published = Date.parse(release.published_at);
    if (!Number.isFinite(published)) return { build: true, reason: `release ${release.tag_name} has no readable publication time` };
    if (published > committedAt) return { build: true, reason: `release ${release.tag_name} was published after the last commit` };
    if (now - published <= RECENT_RELEASE_MS) return { build: true, reason: `release ${release.tag_name} was published within the last 30 minutes` };
  }
  return { build: false, reason: "no site change in the last commit, and every release predates it" };
}

/** The newest releases and the last commit's time, read from GitHub and git. */
async function readInputs() {
  /** @type {Record<string, string>} */
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "shiori-site-ignore-step" };
  // The project's read-only token when Vercel passes it in; anonymous otherwise.
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  // First page, newest first: a release just published is on it.
  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}/releases?per_page=30`, {
    headers,
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`releases request answered ${response.status}`);
  const releases = await response.json();
  if (!Array.isArray(releases)) throw new Error("releases request did not answer a list");
  const committedAt = Number(execFileSync("git", ["show", "-s", "--format=%ct", "HEAD"], { encoding: "utf8" }).trim()) * 1000;
  if (!Number.isFinite(committedAt)) throw new Error("the last commit's time could not be read");
  return { releases, committedAt };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const { build, reason } = await readInputs()
    .then((inputs) => shouldBuild({ ...inputs, now: Date.now() }))
    .catch((error) => ({ build: true, reason: `the release check failed (${error instanceof Error ? error.message : String(error)})` }));
  console.log(`${build ? "Building" : "Skipping"}: ${reason}`);
  // exitCode, not exit(): ending the process under an open fetch socket aborts Node on Windows.
  process.exitCode = build ? 1 : 0;
}
