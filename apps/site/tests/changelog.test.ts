import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import {
  type Fetch,
  type GitHubRelease,
  changelogEntries,
  fetchReleases,
  formatReleaseDate,
  loadReleases,
  parseReleases,
  publishedReleases,
  releaseNotesMarkdown,
  renderReleaseNotes,
} from "../src/lib/changelog";

/*
 * lib/changelog.ts on fixture releases (tests/fixtures/releases.json, in the
 * GitHub API's shape) and a stub `fetch`: no network request.
 */

const fixturePath = resolve(dirname(fileURLToPath(import.meta.url)), "fixtures", "releases.json");
const fixture = parseReleases(JSON.parse(readFileSync(fixturePath, "utf8")), fixturePath);
const release = (tag: string) => {
  const found = fixture.find((entry) => entry.tag_name === tag);
  assert.ok(found, `fixture has no ${tag}`);
  return found;
};

/** A stub `fetch` answering each call from `pages` in turn, recording the calls. */
function stubFetch(pages: (() => Response)[]) {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  const fetch: Fetch = (url, init) => {
    calls.push({ url, headers: init.headers });
    const page = pages[calls.length - 1];
    assert.ok(page, `unexpected request ${calls.length}: ${url}`);
    return Promise.resolve(page());
  };
  return { fetch, calls };
}

const json = (value: unknown) => () => new Response(JSON.stringify(value), { status: 200 });
const someRelease = (n: number): GitHubRelease => ({
  tag_name: `v0.0.${n}`,
  name: null,
  body: null,
  draft: false,
  prerelease: false,
  published_at: "2026-01-01T00:00:00Z",
  html_url: `https://github.com/YinFengWindy/Shiori-Agent/releases/tag/v0.0.${n}`,
});

describe("fetchReleases", () => {
  it("follows the pages until a short one, authenticated with the token", async () => {
    const full = Array.from({ length: 100 }, (_, n) => someRelease(n));
    const { fetch, calls } = stubFetch([json(full), json([someRelease(100)])]);
    const releases = await fetchReleases({ token: "test-token", fetch });
    assert.equal(releases.length, 101);
    assert.deepEqual(
      calls.map((call) => call.url),
      [1, 2].map((page) => `https://api.github.com/repos/YinFengWindy/Shiori-Agent/releases?per_page=100&page=${page}`),
    );
    for (const call of calls) assert.equal(call.headers.Authorization, "Bearer test-token");
  });

  it("goes anonymous without a token", async () => {
    const { fetch, calls } = stubFetch([json([])]);
    await fetchReleases({ token: undefined, fetch });
    assert.equal(calls[0].headers.Authorization, undefined);
  });

  it("fails on a non-2xx answer, such as the rate limit, without leaking the token", async () => {
    const { fetch } = stubFetch([() => new Response('{"message":"API rate limit exceeded"}', { status: 403, statusText: "Forbidden" })]);
    await assert.rejects(fetchReleases({ token: "test-token", fetch }), (error: Error) => {
      assert.match(error.message, /403 Forbidden.*API rate limit exceeded/);
      assert.doesNotMatch(error.message, /test-token/);
      return true;
    });
  });

  it("fails on a network error and on an answer that is not a list of releases", async () => {
    await assert.rejects(fetchReleases({ token: undefined, fetch: () => Promise.reject(new Error("getaddrinfo ENOTFOUND")) }), /ENOTFOUND/);
    await assert.rejects(fetchReleases({ token: undefined, fetch: stubFetch([json({ message: "Not Found" })]).fetch }), /expected an array/);
    await assert.rejects(fetchReleases({ token: undefined, fetch: stubFetch([json([{ tag_name: "v1" }])]).fetch }), /`name` must be a string/);
  });
});

describe("loadReleases", () => {
  const unreachable: Fetch = () => assert.fail("no request expected");

  it("reads the fixture when one is named, never the API", async () => {
    const releases = await loadReleases({ SHIORI_SITE_RELEASES_FIXTURE: fixturePath, CI: "1" }, unreachable);
    assert.deepEqual(releases, fixture);
  });

  it("requires a token on Vercel and in CI", async () => {
    await assert.rejects(loadReleases({ VERCEL: "1" }, unreachable), /GITHUB_TOKEN is not set/);
    await assert.rejects(loadReleases({ CI: "true", GITHUB_TOKEN: "" }, unreachable), /GITHUB_TOKEN is not set/);
  });

  it("asks the API anonymously on a local build without a token", async () => {
    const { fetch, calls } = stubFetch([json([someRelease(1)])]);
    assert.equal((await loadReleases({}, fetch)).length, 1);
    assert.equal(calls.length, 1);
  });
});

describe("publishedReleases", () => {
  it("keeps published full releases only, newest first", () => {
    assert.deepEqual(
      publishedReleases(fixture).map((entry) => entry.tag_name),
      ["v0.5.3", "v0.5.2", "v0.1.0"],
    );
  });
});

describe("releaseNotesMarkdown", () => {
  it("drops a first-line heading naming the version, keeps the sections", () => {
    const notes = releaseNotesMarkdown(release("v0.5.2"));
    assert.doesNotMatch(notes, /^# /m);
    assert.ok(notes.startsWith("## 新增与改进\n"));
    assert.match(notes, /^## 修复$/m);
    assert.match(notes, /^## 升级说明$/m);
  });

  it("drops the 下载 section and its subsections up to the next same-level heading or the end", () => {
    const notes = releaseNotesMarkdown(release("v0.5.2"));
    // The one 下载 line left is the code block's (next test).
    assert.equal(notes.match(/^## 下载$/gm)?.length, 1);
    assert.doesNotMatch(notes, /Shiori-Setup-0\.5\.2\.exe|校验|SHA256SUMS|查看全部变化/);
    const first = releaseNotesMarkdown(release("v0.1.0"));
    assert.equal(first, "## 已知问题\n\n- 首个公开版本，仅支持 Windows x64。");
  });

  it("leaves a 下载 line inside a code block alone", () => {
    assert.match(releaseNotesMarkdown(release("v0.5.2")), /```text\n## 下载\n这一行在代码块里，不是标题。\n```/);
  });

  it("drops HTML comments and keeps a heading that does not name the version", () => {
    const notes = releaseNotesMarkdown(release("v0.5.3"));
    assert.doesNotMatch(notes, /<!--|shiori-daily-release/);
    assert.ok(notes.startsWith("## What's Changed\n"));
    assert.equal(releaseNotesMarkdown({ tag_name: "v1.0.0", name: "v1.0.0", body: "# 春季更新\n\n正文" }), "# 春季更新\n\n正文");
    assert.equal(releaseNotesMarkdown({ tag_name: "v1.0.0", name: "春季更新", body: "# 春季更新\n\n正文" }), "正文");
    assert.equal(releaseNotesMarkdown({ tag_name: "v1.0.0", name: null, body: null }), "");
  });
});

describe("renderReleaseNotes", () => {
  it("starts the notes' headings at h3, under the page's h1 and the version's h2", () => {
    const html = renderReleaseNotes("# 一\n\n## 二\n\n### 三\n\n###### 六");
    assert.equal(html.match(/<h\d>[^<]*<\/h\d>/g)?.join(""), "<h3>一</h3><h3>二</h3><h4>三</h4><h6>六</h6>");
  });

  it("marks links off the site rel=noopener, autolinked ones included", () => {
    const html = renderReleaseNotes("[契约](https://github.com/a/b) 和 [首页](/) 见 https://www.npmjs.com/x");
    assert.match(html, /<a href="https:\/\/github\.com\/a\/b" rel="noopener">契约<\/a>/);
    assert.match(html, /<a href="\/">首页<\/a>/);
    assert.match(html, /<a href="https:\/\/www\.npmjs\.com\/x" rel="noopener">https:\/\/www\.npmjs\.com\/x<\/a>/);
  });
});

describe("changelogEntries", () => {
  it("turns the published releases into entries: version, moment, GitHub page and cleaned-up HTML", () => {
    const entries = changelogEntries(fixture);
    assert.deepEqual(
      entries.map(({ version, publishedAt, url }) => ({ version, publishedAt: publishedAt.toISOString(), url })),
      [
        { version: "v0.5.3", publishedAt: "2026-10-10T10:36:03.000Z", url: "https://github.com/YinFengWindy/Shiori-Agent/releases/tag/v0.5.3" },
        { version: "v0.5.2", publishedAt: "2026-10-09T16:41:11.000Z", url: "https://github.com/YinFengWindy/Shiori-Agent/releases/tag/v0.5.2" },
        { version: "v0.1.0", publishedAt: "2026-08-23T14:09:49.000Z", url: "https://github.com/YinFengWindy/Shiori-Agent/releases/tag/v0.1.0" },
      ],
    );
    assert.match(entries[1].html, /^<h3>新增与改进<\/h3>/);
  });
});

describe("formatReleaseDate", () => {
  it("reads the day in Beijing time", () => {
    assert.equal(formatReleaseDate(new Date("2026-10-09T16:41:11Z")), "2026年10月10日");
  });
});
