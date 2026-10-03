import assert from "node:assert/strict";
import test from "node:test";
import { planDailyRelease } from "./daily-release-policy.mjs";
import { publishDailyRelease, readDailyState } from "./daily-release-publish.mjs";
import { releaseRepository, releaseServer } from "./daily-release-test-fixtures.mjs";

const files = [{ name: "installer.exe", size: 12, digest: "sha256:first-build" }];
async function candidate(t) {
  const repo = releaseRepository(t);
  for (let count = 0; count < 5; count += 1) repo.commit();
  const server = releaseServer(repo);
  const plan = planDailyRelease(await readDailyState(repo.git, server.github, repo.git.resolve("HEAD"))).plan;
  return { repo, ...server, input: { plan, files, git: repo.git, github: server.github } };
}

test("publication uploads and verifies before tagging, preserves initial draft and is idempotent", async (t) => {
  const fixture = await candidate(t);
  const { repo, input, releases, events } = fixture;
  assert.equal(await publishDailyRelease(input), "published");
  assert.deepEqual(events, ["draft", "upload", "tag", "publish"]);
  assert.equal(releases[0].draft, true);
  assert.equal(releases[0].body, "Keep this manual draft");
  assert.equal(repo.git.tags().get(input.plan.tag), input.plan.sha);
  assert.equal(await publishDailyRelease(input), "already-published");
  assert.equal(events.length, 4);
});

test("failed upload then next-day main advance resumes old SHA and replaces partial assets", async (t) => {
  const { repo, github, input, releases, assets, events } = await candidate(t);
  const upload = github.upload;
  github.upload = async (id, file) => {
    await upload(id, file);
    throw new Error("upload connection lost");
  };
  await assert.rejects(publishDailyRelease(input), /connection lost/);
  assert.equal(repo.git.tags().has(input.plan.tag), false);
  assert.equal(releases[1].draft, true);
  const newerHead = repo.commit();
  const nextDay = planDailyRelease(await readDailyState(repo.git, github, newerHead));
  assert.deepEqual(nextDay.plan, input.plan);
  repo.run("checkout", "--detach", input.plan.sha);
  assets.push({ id: 999, name: "interrupted", state: "starter" });
  github.upload = upload;
  const rebuilt = [{ ...files[0], digest: "sha256:rebuilt-bytes" }];
  assert.equal(await publishDailyRelease({ ...input, files: rebuilt }), "published");
  assert.equal(events.filter((event) => event === "draft").length, 1);
  assert.equal(events.filter((event) => event === "delete-asset").length, 2);
  assert.equal(assets[0].digest, rebuilt[0].digest);
  const after = planDailyRelease(await readDailyState(repo.git, github, newerHead));
  assert.equal(after.shouldRelease, false);
  assert.equal(after.plan.commitCount, 1);
  assert.equal(after.plan.baselineTag, input.plan.tag);
});

test("publish failure after tag creation retains baseline and allows retry", async (t) => {
  const { repo, github, input } = await candidate(t);
  const publish = github.publish;
  github.publish = async () => { throw new Error("publication unavailable"); };
  await assert.rejects(publishDailyRelease(input), /unavailable/);
  assert.equal(repo.git.tags().get(input.plan.tag), input.plan.sha);
  assert.deepEqual(planDailyRelease(await readDailyState(repo.git, github, input.plan.sha)).plan, input.plan);
  github.publish = publish;
  assert.equal(await publishDailyRelease(input), "published");
});

test("ambiguous successful publish is reconciled on retry without overwriting public assets", async (t) => {
  const { github, input, events } = await candidate(t);
  const publish = github.publish;
  github.publish = async (id) => { await publish(id); throw new Error("response lost"); };
  await assert.rejects(publishDailyRelease(input), /response lost/);
  const mutations = events.length;
  assert.equal(await publishDailyRelease(input), "already-published");
  assert.equal(events.length, mutations);
});

test("remote hash mismatch prevents creating tag or publishing", async (t) => {
  const { github, input, assets, events } = await candidate(t);
  const upload = github.upload;
  github.upload = async (id, file) => { await upload(id, file); assets[0].digest = "sha256:wrong"; };
  await assert.rejects(publishDailyRelease(input), /verification failed/);
  assert.deepEqual(events, ["draft", "upload"]);
});

test("release state changed during upload prevents publication", async (t) => {
  const { repo, github, input, releases, events } = await candidate(t);
  const upload = github.upload;
  github.upload = async (id, file) => {
    await upload(id, file);
    repo.run("tag", "v0.5.2");
    releases.push({ id: 900, tag_name: "v0.5.2", draft: false });
  };
  await assert.rejects(publishDailyRelease(input), /plan is stale/);
  assert.deepEqual(events, ["draft", "upload"]);
});

test("wrong build SHA and pre-existing public or manual releases fail before mutations", async (t) => {
  const { repo, input, releases, events } = await candidate(t);
  repo.commit();
  await assert.rejects(publishDailyRelease(input), /checkout does not match/);
  repo.run("checkout", "--detach", input.plan.sha);
  releases.push({ id: 900, tag_name: input.plan.tag, draft: false, body: "manual" });
  await assert.rejects(publishDailyRelease(input), /Published release conflict/);
  releases[1].draft = true;
  await assert.rejects(publishDailyRelease(input), /not an automatic draft/);
  assert.deepEqual(events, []);
});
