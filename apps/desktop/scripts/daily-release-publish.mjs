import { dailyPlanMarker, planDailyRelease, readDailyPlan, sameDailyPlan } from "./daily-release-policy.mjs";
import { verifyDailyAssets } from "./daily-release-assets.mjs";

/** Refreshes Git and Releases together, checking the pinned source remains on main. */
export async function readDailyState(git, github, sha) {
  git.refresh();
  git.assertAncestor(sha, git.resolve("origin/main"));
  return { tags: git.tags(), releases: await github.releases(), head: sha, git };
}

async function guardPlan(plan, git, github) {
  const state = await readDailyState(git, github, plan.sha);
  const release = state.releases.find((item) => item.tag_name === plan.tag);
  if (release && !release.draft) {
    if (release.prerelease || !sameDailyPlan(readDailyPlan(release), plan)
      || state.tags.get(plan.tag) !== plan.sha) {
      throw new Error(`Published release conflict: ${plan.tag}`);
    }
    return { state, release, completed: true };
  }
  const current = planDailyRelease(state);
  if (!current.shouldRelease || !sameDailyPlan(current.plan, plan)) {
    throw new Error(`Release plan is stale: ${plan.tag}`);
  }
  return { state, release, completed: false };
}

/** Publishes only verified assets; failed owned drafts are safely rebuilt on the same SHA. */
export async function publishDailyRelease({ plan, files, git, github }) {
  if (git.resolve("HEAD") !== plan.sha) throw new Error("Build checkout does not match release plan");
  let guarded = await guardPlan(plan, git, github);
  if (guarded.completed) return "already-published";
  const draft = guarded.release ?? await github.createDraft(plan, dailyPlanMarker(plan));
  guarded = await guardPlan(plan, git, github);
  if (guarded.completed || guarded.release?.id !== draft.id) throw new Error("Draft changed before upload");
  // Rebuilds are not byte-reproducible. Replace only this owned, still-private draft's
  // assets (including interrupted starter uploads), never any published release assets.
  for (const asset of await github.assets(draft.id)) await github.deleteAsset(asset.id);
  for (const file of files) await github.upload(draft.id, file);
  verifyDailyAssets(files, await github.assets(draft.id));
  guarded = await guardPlan(plan, git, github);
  if (guarded.completed || guarded.release?.id !== draft.id) throw new Error("Draft changed before publication");
  // A failed upload never reserves a tag. A late failure can reuse the owned tag,
  // but that tag alone never advances the next run's successful-release baseline.
  if (!guarded.state.tags.has(plan.tag)) await github.createTag(plan);
  guarded = await guardPlan(plan, git, github);
  if (guarded.completed || guarded.release?.id !== draft.id
    || guarded.state.tags.get(plan.tag) !== plan.sha) throw new Error("Tag or draft changed before publication");
  verifyDailyAssets(files, await github.assets(draft.id));
  const released = await github.publish(draft.id);
  if (released.draft || released.prerelease || released.tag_name !== plan.tag) {
    throw new Error("GitHub did not confirm a stable public release");
  }
  return "published";
}
