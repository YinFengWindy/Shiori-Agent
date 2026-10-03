import { resolveReleaseVersion } from "./release-version.mjs";

const initialTag = "v0.5.0";
const marker = /<!-- shiori-daily-release:(\{[^\n]+\}) -->/;

/** Recognizes only stable desktop tags, excluding SDK and prerelease tags. */
export function stableVersion(tag) {
  return /^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(tag)
    ? resolveReleaseVersion(tag.slice(1)) : undefined;
}

function compareTags(left, right) {
  const a = stableVersion(left).split(".").map(BigInt);
  const b = stableVersion(right).split(".").map(BigInt);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] > b[index] ? 1 : -1;
  }
  return 0;
}

/** Advances decimal desktop versions, carrying patch and minor at ten. */
export function nextDailyVersion(tag) {
  if (!stableVersion(tag)) throw new Error(`Invalid stable desktop tag: ${tag}`);
  const [major, minor, patch] = tag.slice(1).split(".").map(BigInt);
  if (minor > 9n || patch > 9n) throw new Error(`Not a decimal desktop version: ${tag}`);
  const next = major * 100n + minor * 10n + patch + 1n;
  return `${next / 100n}.${(next / 10n) % 10n}.${next % 10n}`;
}

/** Reads the immutable plan identifying a draft owned by this automation. */
export function readDailyPlan(release) {
  const match = release?.body?.match(marker);
  return match ? JSON.parse(match[1]) : undefined;
}

/** Embeds the release provenance without exposing it in rendered release notes. */
export function dailyPlanMarker(plan) {
  return `<!-- shiori-daily-release:${JSON.stringify(plan)} -->`;
}

/** Compares every field in a stored plan, rejecting missing or extra provenance. */
export function sameDailyPlan(left, right) {
  return left && right && Object.keys(left).length === Object.keys(right).length
    && Object.keys(left).every((key) => left[key] === right[key]);
}

/** Plans from published releases and full Git history; skipped days retain the baseline. */
export function planDailyRelease({ releases, tags, head, git }) {
  const published = releases.filter((release) => !release.draft && !release.prerelease
    && stableVersion(release.tag_name) && compareTags(release.tag_name, initialTag) >= 0);
  const baselineTag = published.map((release) => release.tag_name)
    .sort(compareTags).at(-1) ?? initialTag;
  const baselineSha = tags.get(baselineTag);
  if (!baselineSha) throw new Error(`Missing baseline tag: ${baselineTag}`);
  git.assertAncestor(baselineSha, head);
  const version = nextDailyVersion(baselineTag);
  const tag = `v${version}`;
  const candidate = releases.find((release) => release.tag_name === tag);
  const prereleaseTags = new Set(releases.filter((release) => release.prerelease).map((release) => release.tag_name));
  const reserved = new Set([...tags.keys(), ...releases.map((release) => release.tag_name)]);
  for (const reservedTag of reserved) {
    if (!prereleaseTags.has(reservedTag) && stableVersion(reservedTag) && compareTags(reservedTag, baselineTag) > 0
      && reservedTag !== tag) throw new Error(`Conflicting stable version: ${reservedTag}`);
  }
  const stored = readDailyPlan(candidate);
  if (candidate && (!candidate.draft || candidate.prerelease || !stored)) {
    throw new Error(`Release ${tag} is not an automatic draft`);
  }
  // Resume the failed draft's original commit even when main has since advanced.
  const sha = stored?.sha ?? head;
  if (!/^[a-f0-9]{40}$/.test(sha)) throw new Error("Invalid release commit SHA");
  git.assertAncestor(baselineSha, sha);
  git.assertAncestor(sha, head);
  const commitCount = git.count(baselineSha, sha);
  const plan = { baselineTag, baselineSha, sha, tag, version, commitCount };
  if (stored && (!sameDailyPlan(stored, plan) || candidate.target_commitish !== sha)) {
    throw new Error(`Automatic draft provenance conflict: ${tag}`);
  }
  if (tags.has(tag) && (!stored || tags.get(tag) !== sha)) {
    throw new Error(`Tag conflict: ${tag}`);
  }
  if (stored && commitCount < 5) throw new Error(`Invalid draft commit count: ${tag}`);
  return { shouldRelease: commitCount >= 5, plan };
}
