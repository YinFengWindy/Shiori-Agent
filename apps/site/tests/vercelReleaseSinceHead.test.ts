import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { RECENT_RELEASE_MS, shouldBuild } from "../scripts/vercel-release-since-head.mjs";

/*
 * The Vercel ignore step's release rule (scripts/vercel-release-since-head.mjs)
 * on given releases, commit time and clock: no network, no git.
 */

const minute = 60 * 1000;
const at = (iso: string) => Date.parse(iso);
const release = (tag: string, publishedAt: string | null, draft = false) => ({ tag_name: tag, draft, published_at: publishedAt });

describe("shouldBuild", () => {
  const releases = [release("v0.6.0", null, true), release("v0.5.3", "2026-10-10T10:36:03Z"), release("v0.5.2", "2026-10-09T16:41:11Z")];

  it("builds for a release published after the last commit (the hook right after a release)", () => {
    const decision = shouldBuild({ releases, committedAt: at("2026-10-10T10:06:58Z"), now: at("2026-10-10T10:37:00Z") });
    assert.deepEqual(decision, { build: true, reason: "release v0.5.3 was published after the last commit" });
  });

  it("builds for a release published within 30 minutes, though a non-site commit landed after it", () => {
    const committedAt = at("2026-10-10T10:40:00Z");
    assert.equal(shouldBuild({ releases, committedAt, now: at("2026-10-10T10:36:03Z") + RECENT_RELEASE_MS }).build, true);
    assert.equal(shouldBuild({ releases, committedAt, now: at("2026-10-10T10:36:03Z") + RECENT_RELEASE_MS + minute }).build, false);
  });

  it("looks past the newest release: one not marked latest counts too", () => {
    const listed = [release("v0.4.9", "2026-10-08T00:00:00Z"), release("v0.5.3", "2026-10-10T10:36:03Z")];
    assert.equal(shouldBuild({ releases: listed, committedAt: at("2026-10-10T10:00:00Z"), now: at("2026-10-12T00:00:00Z") }).build, true);
  });

  it("skips when every published release predates the last commit and the window, drafts ignored", () => {
    const decision = shouldBuild({ releases, committedAt: at("2026-10-13T04:00:00Z"), now: at("2026-10-13T05:00:00Z") });
    assert.equal(decision.build, false);
    assert.equal(shouldBuild({ releases: [], committedAt: 0, now: 0 }).build, false);
  });

  it("builds when a release's time cannot be read", () => {
    assert.equal(shouldBuild({ releases: [release("v1", "not a date")], committedAt: 0, now: 0 }).build, true);
  });
});
