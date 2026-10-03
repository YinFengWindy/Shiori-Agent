import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createReleaseGitHub } from "./daily-release-github.mjs";

function client(fetchImpl) {
  return createReleaseGitHub({ token: "test-token", repository: "owner/repo", fetchImpl });
}

test("release listing paginates and finds drafts without the misleading tag endpoint", async () => {
  const urls = [];
  const github = client(async (url, options) => {
    urls.push(url);
    assert.equal(options.headers.Authorization, "Bearer test-token");
    return Response.json(new URL(url).searchParams.get("page") === "1"
      ? Array.from({ length: 100 }, (_, id) => ({ id, tag_name: `sdk-v${id}.0.0` }))
      : [{ id: 101, tag_name: "v0.5.0", draft: true }]);
  });
  const releases = await github.releases();
  assert.equal(releases.length, 101);
  assert.equal(releases.at(-1).draft, true);
  assert.deepEqual(urls, [
    "https://api.github.com/repos/owner/repo/releases?per_page=100&page=1",
    "https://api.github.com/repos/owner/repo/releases?per_page=100&page=2",
  ]);
});

test("authentication, not-found, rate-limit and server errors are not empty release history", async () => {
  for (const status of [401, 403, 404, 429, 500]) {
    const github = client(async () => new Response("failure", { status }));
    await assert.rejects(github.releases(), new RegExp(String(status)));
  }
});

test("draft, notes, tag and promotion APIs carry the pinned source and stable flags", async () => {
  const calls = [];
  const github = client(async (url, options) => {
    calls.push({ url, method: options.method, body: options.body && JSON.parse(options.body) });
    return Response.json(url.endsWith("generate-notes") ? { body: "Changes" } : { id: 7 });
  });
  const plan = { tag: "v0.5.1", sha: "a".repeat(40), baselineTag: "v0.5.0" };
  await github.createDraft(plan, "provenance");
  await github.createTag(plan);
  await github.publish(7);
  assert.deepEqual(calls.map((call) => call.method), ["POST", "POST", "POST", "PATCH"]);
  assert.equal(calls[0].body.previous_tag_name, "v0.5.0");
  assert.equal(calls[0].body.target_commitish, plan.sha);
  assert.equal(calls[1].body.target_commitish, plan.sha);
  assert.equal(calls[1].body.draft, true);
  assert.equal(calls[1].body.body, "provenance\n\nChanges");
  assert.deepEqual(calls[2].body, { ref: "refs/tags/v0.5.1", sha: plan.sha });
  assert.deepEqual(calls[3].body, { draft: false, prerelease: false, make_latest: "true" });
});

test("upload streams the exact bytes and deletion accepts GitHub's empty 204 response", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "shiori-upload-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const path = join(directory, "Shiori Setup.exe");
  await writeFile(path, "installer", "utf8");
  const github = client(async (url, options) => {
    if (options.method === "DELETE") return new Response(null, { status: 204 });
    assert.equal(url, "https://uploads.github.com/repos/owner/repo/releases/7/assets?name=Shiori%20Setup.exe");
    assert.equal(options.headers["Content-Length"], "9");
    const chunks = [];
    for await (const chunk of options.body) chunks.push(chunk);
    assert.equal(Buffer.concat(chunks).toString("utf8"), "installer");
    return Response.json({ state: "uploaded" });
  });
  assert.equal((await github.upload(7, { name: "Shiori Setup.exe", path, size: 9 })).state, "uploaded");
  assert.equal(await github.deleteAsset(8), undefined);
});
