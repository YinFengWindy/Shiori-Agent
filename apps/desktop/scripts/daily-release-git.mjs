import { execFileSync, spawnSync } from "node:child_process";
import { stableVersion } from "./daily-release-policy.mjs";

/** Owns full-history Git reads and refreshes; never pushes or rewrites a tag. */
export function createReleaseGit(cwd = process.cwd()) {
  const run = (...args) => execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
  return {
    resolve: (ref) => run("rev-parse", "--verify", `${ref}^{commit}`),
    count: (base, head) => Number(run("rev-list", "--count", `${base}..${head}`)),
    assertAncestor(base, head) {
      const result = spawnSync("git", ["merge-base", "--is-ancestor", base, head], { cwd });
      if (result.error) throw result.error;
      if (result.status !== 0) throw new Error(`Commit ${base} is not an ancestor of ${head}`);
    },
    refresh() {
      if (run("rev-parse", "--is-shallow-repository") !== "false") {
        throw new Error("Daily releases require complete Git history");
      }
      // Refuse remote tag rewrites. main may advance while the pinned build runs.
      run("fetch", "origin", "+refs/heads/main:refs/remotes/origin/main", "refs/tags/*:refs/tags/*");
    },
    tags() {
      // Reconcile the remote inventory too: a deleted remote tag must not survive
      // as a successful baseline merely because fetch retained its local copy.
      const refs = new Map(run("ls-remote", "--tags", "origin").split("\n")
        .filter(Boolean).map((line) => { const [sha, ref] = line.split("\t"); return [ref, sha]; }));
      return new Map([...refs].filter(([ref]) => stableVersion(ref.replace("refs/tags/", "")))
        .map(([ref, sha]) => [ref.slice("refs/tags/".length), refs.get(`${ref}^{}`) ?? sha]));
    },
  };
}
