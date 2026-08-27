import type { RoleRecord } from "../shared/types";

/** One role-owned image that can be considered for the Story menu backdrop. */
export type StoryMenuAssetCandidate = {
  roleId: string;
  assetPath: string;
  assetUrl: string;
};

/** Minimal image surface used to probe natural dimensions without coupling selection to the DOM. */
export type StoryMenuImageProbe = Pick<HTMLImageElement, "naturalWidth" | "naturalHeight" | "src" | "onload" | "onerror">;

/** Factory used by the background resolver to create an image probe. */
export type StoryMenuImageFactory = () => StoryMenuImageProbe;

/** Resolves renderer-safe URLs for role-owned absolute asset paths. */
export type StoryMenuAssetUrlResolver = (path: string) => string;

/** Collects each role's illustration library entry while preserving role ownership. */
export function collectStoryMenuAssetCandidates(
  roles: readonly Pick<RoleRecord, "id" | "illustrations_abs">[],
  resolveAssetUrl: StoryMenuAssetUrlResolver,
): StoryMenuAssetCandidate[] {
  return roles.flatMap((role) => role.illustrations_abs
    .filter((assetPath) => Boolean(assetPath))
    .map((assetPath) => ({
      roleId: role.id,
      assetPath,
      assetUrl: resolveAssetUrl(assetPath),
    })));
}

/** Loads candidates in parallel and keeps only images whose natural width exceeds height. */
export async function loadLandscapeStoryMenuAssets(
  candidates: readonly StoryMenuAssetCandidate[],
  createImage: StoryMenuImageFactory,
): Promise<StoryMenuAssetCandidate[]> {
  const results = await Promise.all(candidates.map((candidate) => new Promise<StoryMenuAssetCandidate | null>((resolve) => {
    const image = createImage();
    image.onload = () => resolve(image.naturalWidth > image.naturalHeight ? candidate : null);
    image.onerror = () => resolve(null);
    image.src = candidate.assetUrl;
  })));
  return results.filter((candidate): candidate is StoryMenuAssetCandidate => candidate !== null);
}

/** Chooses one role uniformly, then one landscape image uniformly from that role. */
export function chooseRandomStoryMenuAsset(
  candidates: readonly StoryMenuAssetCandidate[],
  random: () => number = Math.random,
): StoryMenuAssetCandidate | null {
  const assetsByRole = new Map<string, StoryMenuAssetCandidate[]>();
  for (const candidate of candidates) {
    const roleAssets = assetsByRole.get(candidate.roleId) ?? [];
    roleAssets.push(candidate);
    assetsByRole.set(candidate.roleId, roleAssets);
  }
  const roleGroups = [...assetsByRole.values()];
  if (!roleGroups.length) return null;
  const roleAssets = roleGroups[randomIndex(roleGroups.length, random)]!;
  return roleAssets[randomIndex(roleAssets.length, random)] ?? null;
}

function randomIndex(length: number, random: () => number): number {
  const value = random();
  const normalized = Number.isFinite(value) ? Math.min(Math.max(value, 0), 0.999999999) : 0;
  return Math.floor(normalized * length);
}
