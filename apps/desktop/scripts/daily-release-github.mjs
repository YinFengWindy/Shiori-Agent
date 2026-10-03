import { createReadStream } from "node:fs";

/** Authenticated GitHub boundary with explicit pagination and fail-fast errors. */
export function createReleaseGitHub({ token, repository, fetchImpl = fetch }) {
  if (!token || !/^[\w.-]+\/[\w.-]+$/.test(repository)) {
    throw new Error("GITHUB_TOKEN and GITHUB_REPOSITORY are required");
  }
  const root = `https://api.github.com/repos/${repository}`;
  async function request(method, url, body, headers = {}) {
    const response = await fetchImpl(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        ...headers,
      },
      ...(body === undefined ? {} : { body: headers["Content-Length"] ? body : JSON.stringify(body) }),
      ...(headers["Content-Length"] ? { duplex: "half" } : {}),
    });
    if (!response.ok) throw new Error(`GitHub ${method} ${url}: ${response.status} ${await response.text()}`);
    return response.status === 204 ? undefined : response.json();
  }
  const api = (method, path, body) => request(method, `${root}/${path}`, body);
  async function pages(path) {
    const items = [];
    for (let page = 1; ; page += 1) {
      const batch = await api("GET", `${path}?per_page=100&page=${page}`);
      items.push(...batch);
      if (batch.length < 100) return items;
    }
  }
  return {
    // The tag endpoint returns 404 for drafts; only this paginated list reconciles them.
    releases: () => pages("releases"),
    assets: (id) => pages(`releases/${id}/assets`),
    deleteAsset: (id) => api("DELETE", `releases/assets/${id}`),
    async createDraft(plan, body) {
      const notes = await api("POST", "releases/generate-notes", {
        tag_name: plan.tag, target_commitish: plan.sha, previous_tag_name: plan.baselineTag,
      });
      return api("POST", "releases", {
        tag_name: plan.tag, target_commitish: plan.sha, name: plan.tag,
        body: `${body}\n\n${notes.body}`, draft: true, prerelease: false,
      });
    },
    createTag: (plan) => api("POST", "git/refs", { ref: `refs/tags/${plan.tag}`, sha: plan.sha }),
    upload(id, file) {
      const url = `https://uploads.github.com/repos/${repository}/releases/${id}/assets?name=${encodeURIComponent(file.name)}`;
      return request("POST", url, createReadStream(file.path), {
        "Content-Type": "application/octet-stream", "Content-Length": String(file.size),
      });
    },
    publish: (id) => api("PATCH", `releases/${id}`, { draft: false, prerelease: false, make_latest: "true" }),
  };
}
