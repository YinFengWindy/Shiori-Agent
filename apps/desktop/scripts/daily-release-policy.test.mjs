import assert from "node:assert/strict";
import test from "node:test";
import { dailyPlanMarker, nextDailyVersion, planDailyRelease, stableVersion } from "./daily-release-policy.mjs";
import { releaseRepository } from "./daily-release-test-fixtures.mjs";

function plan(repo, releases = []) {
  return planDailyRelease({ git: repo.git, tags: repo.git.tags(), head: repo.git.resolve("HEAD"), releases });
}

test("decimal versions carry and stable tags exclude SDK/prereleases/build metadata", () => {
  assert.equal(nextDailyVersion("v0.5.0"), "0.5.1");
  assert.equal(nextDailyVersion("v0.5.9"), "0.6.0");
  assert.equal(nextDailyVersion("v0.9.9"), "1.0.0");
  assert.equal(nextDailyVersion("v12.9.9"), "13.0.0");
  assert.throws(() => nextDailyVersion("v1.10.0"), /decimal/);
  for (const tag of ["sdk-v9.0.0", "v1.0.0-rc.1", "v1.0.0+build", "v01.0.0", "v1.0"]) {
    assert.equal(stableVersion(tag), undefined);
  }
});

test("zero through four commits skip across days; five and above release from v0.5.0", (t) => {
  const repo = releaseRepository(t);
  for (let count = 0; count <= 6; count += 1) {
    const today = plan(repo);
    const tomorrow = plan(repo);
    assert.deepEqual(today, tomorrow);
    assert.equal(today.shouldRelease, count >= 5);
    assert.equal(today.plan.commitCount, count);
    assert.equal(today.plan.tag, "v0.5.1");
    assert.equal(today.plan.baselineTag, "v0.5.0");
    repo.commit();
  }
});

test("full reachability count includes merged branch commits and the merge commit", (t) => {
  const repo = releaseRepository(t);
  repo.run("checkout", "-b", "feature");
  repo.commit();
  repo.commit();
  repo.run("checkout", "main");
  repo.commit();
  repo.commit();
  repo.run("merge", "--no-ff", "feature", "-m", "merge feature");
  assert.equal(plan(repo).plan.commitCount, 5);
  assert.equal(plan(repo).shouldRelease, true);
});

test("published stable releases advance baseline; SDK, prereleases and initial draft do not", (t) => {
  const repo = releaseRepository(t);
  repo.commit();
  repo.run("tag", "v0.5.9");
  repo.run("tag", "sdk-v50.0.0");
  repo.run("tag", "v9.0.0-rc.1");
  repo.run("tag", "v9.0.0");
  const releases = [
    { tag_name: "v0.4.0", draft: false, prerelease: false },
    { tag_name: "v0.5.0", draft: true, prerelease: false },
    { tag_name: "v0.5.9", draft: false, prerelease: false },
    { tag_name: "sdk-v50.0.0", draft: false, prerelease: false },
    { tag_name: "v9.0.0-rc.1", draft: false, prerelease: true },
    { tag_name: "v9.0.0", draft: false, prerelease: true },
  ];
  repo.commit();
  assert.equal(plan(repo, releases).plan.commitCount, 1);
  assert.equal(plan(repo, releases).plan.tag, "v0.6.0");
});

test("missing or divergent baselines stop instead of silently resetting history", (t) => {
  const repo = releaseRepository(t);
  assert.throws(() => plan(repo, [{ tag_name: "v0.6.0", draft: false }]), /Missing baseline/);
  repo.run("checkout", "--orphan", "other");
  repo.commit();
  assert.throws(() => plan(repo), /not an ancestor/);
});

test("owned failed draft resumes its pinned SHA after main advances", (t) => {
  const repo = releaseRepository(t);
  for (let count = 0; count < 5; count += 1) repo.commit();
  const original = plan(repo).plan;
  repo.commit();
  const draft = { tag_name: original.tag, target_commitish: original.sha, draft: true, body: dailyPlanMarker(original) };
  assert.deepEqual(plan(repo, [draft]).plan, original);
  const corrupted = { ...draft, body: dailyPlanMarker({ ...original, commitCount: 9 }) };
  assert.throws(() => plan(repo, [corrupted]), /provenance conflict/);
});

test("manual drafts and unowned or mismatched tags conflict without consuming baseline", (t) => {
  const repo = releaseRepository(t);
  for (let count = 0; count < 5; count += 1) repo.commit();
  const original = plan(repo).plan;
  assert.throws(() => plan(repo, [{ tag_name: original.tag, draft: true, body: "manual" }]), /not an automatic draft/);
  repo.run("tag", original.tag);
  assert.throws(() => plan(repo), /Tag conflict/);
  const draft = { tag_name: original.tag, target_commitish: original.sha, draft: true, body: dailyPlanMarker(original) };
  assert.deepEqual(plan(repo, [draft]).plan, original);
  repo.run("tag", "-f", original.tag, "v0.5.0");
  assert.throws(() => plan(repo, [draft]), /Tag conflict/);
});
