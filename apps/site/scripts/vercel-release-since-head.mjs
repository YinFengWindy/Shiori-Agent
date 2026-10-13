// Second half of the Vercel ignore step (vercel-ignore-build.sh), run when
// the last commit changed nothing of the site: builds (exit 1) when the
// newest published release came out after that commit, so the changelog
// (/changelog/, #792) would be missing it; skips (exit 0) otherwise. Any
// failure to tell — network, rate limit, an unexpected answer — builds.
// Node built-ins only: the ignore step runs before dependencies install.
import { execFileSync } from "node:child_process";

const REPOSITORY = "YinFengWindy/Shiori-Agent";

/** Whether to build, and why. */
async function decide() {
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "shiori-site-ignore-step" };
  // The project's read-only token when Vercel passes it in; anonymous otherwise.
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}/releases/latest`, {
    headers,
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) return { build: true, reason: `the latest release could not be read (${response.status})` };
  const { tag_name: tag, published_at: publishedAt } = await response.json();
  const published = Date.parse(publishedAt);
  const committed = Number(execFileSync("git", ["show", "-s", "--format=%ct", "HEAD"], { encoding: "utf8" }).trim()) * 1000;
  if (!Number.isFinite(published) || !Number.isFinite(committed)) {
    return { build: true, reason: "the release or commit time could not be read" };
  }
  if (published > committed) return { build: true, reason: `release ${tag} was published after the last commit` };
  return { build: false, reason: `no site change in the last commit, and release ${tag} predates it` };
}

const { build, reason } = await decide().catch((error) => ({
  build: true,
  reason: `the release check failed (${error instanceof Error ? error.message : String(error)})`,
}));
console.log(`${build ? "Building" : "Skipping"}: ${reason}`);
// exitCode, not exit(): ending the process under an open fetch socket aborts Node on Windows.
process.exitCode = build ? 1 : 0;
