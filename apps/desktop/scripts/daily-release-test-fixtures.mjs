import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createReleaseGit } from "./daily-release-git.mjs";

/** Creates a real complete Git graph whose origin is local, without network writes. */
export function releaseRepository(t) {
  const directory = mkdtempSync(join(tmpdir(), "shiori-daily-release-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const run = (...args) => execFileSync("git", args, { cwd: directory, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
  run("init", "--initial-branch=main");
  run("config", "user.email", "release-tests@example.invalid");
  run("config", "user.name", "Release Tests");
  run("config", "commit.gpgsign", "false");
  run("config", "tag.gpgsign", "false");
  run("remote", "add", "origin", directory);
  let counter = 0;
  const commit = () => {
    run("commit", "--allow-empty", "-m", `commit ${counter++}`);
    return run("rev-parse", "HEAD");
  };
  commit();
  run("tag", "-a", "v0.5.0", "-m", "initial baseline");
  return { directory, run, commit, git: createReleaseGit(directory) };
}

/** In-memory GitHub server boundary for publication transaction tests. */
export function releaseServer(repo) {
  const releases = [{ id: 50, tag_name: "v0.5.0", draft: true, prerelease: false, body: "Keep this manual draft" }];
  const assets = [];
  const events = [];
  let nextId = 100;
  const github = {
    releases: async () => structuredClone(releases),
    assets: async () => structuredClone(assets),
    async createDraft(plan, body) {
      events.push("draft");
      const release = { id: nextId++, tag_name: plan.tag, target_commitish: plan.sha, draft: true, prerelease: false, body };
      releases.push(release);
      return structuredClone(release);
    },
    async deleteAsset(id) {
      events.push("delete-asset");
      assets.splice(assets.findIndex((asset) => asset.id === id), 1);
    },
    async upload(id, file) {
      events.push("upload");
      assets.push({ id: nextId++, name: file.name, size: file.size, digest: file.digest, state: "uploaded" });
    },
    async createTag(plan) {
      events.push("tag");
      repo.run("tag", plan.tag, plan.sha);
    },
    async publish(id) {
      events.push("publish");
      const release = releases.find((item) => item.id === id);
      release.draft = false;
      return structuredClone(release);
    },
  };
  return { github, releases, assets, events };
}
