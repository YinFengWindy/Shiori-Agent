/** Refuse to distribute an unfinalized or previously used SDK contract version. */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { syncSdkVersion } from "./sync_sdk_version.mjs";

const versionPath = "packages/sdk/python/shiori_sdk/_version.py";
const stableVersion = "(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)";
const releaseTag = new RegExp(`^(sdk-v|v)${stableVersion}$`);

function versionFrom(source) {
  const version = source.match(/^__version__ = "([^"]+)"\r?$/m)?.[1];
  if (!version || !new RegExp(`^${stableVersion}$`).test(version)) {
    throw new Error("SDK releases require a stable X.Y.Z version");
  }
  return version;
}

function compareVersions(left, right) {
  const a = left.split(".").map(BigInt);
  const b = right.split(".").map(BigInt);
  for (let index = 0; index < 3; index++) {
    if (a[index] !== b[index]) return a[index] > b[index] ? 1 : -1;
  }
  return 0;
}

// Public testing helpers are shipped API; only actual tests and documentation
// are omitted. Build scripts/metadata also affect the distributed contract.
function contractPath(path) {
  if (!path.startsWith("packages/sdk/")) return false;
  const parts = path.split("/");
  if (parts.some((part) => ["tests", "docs", "node_modules", "dist", "build", "__pycache__"].includes(part) || part.endsWith(".egg-info"))) return false;
  const name = parts.at(-1);
  return !/\.(?:test|spec)\.[^/]+$|\.py[co]$|\.(?:md|rst)$/i.test(name) && !/^(?:README|LICENSE|NOTICE)(?:\.|$)/i.test(name);
}

function requireFinalizedNotes(root) {
  const notes = readFileSync(join(root, "docs/_handbook/plugin-runtime-contract.md"), "utf8");
  const headings = [...notes.matchAll(/^### Unreleased\s*$/gm)];
  if (headings.length !== 1) throw new Error("Expected exactly one SDK Unreleased section");
  const rest = notes.slice(headings[0].index + headings[0][0].length);
  const section = rest.split(/^#{1,3} /m)[0].replace(/<!--[\s\S]*?-->/g, "").trim();
  if (section) throw new Error("SDK Unreleased is not empty; finalize this contract batch before release");
}

/** Check working-tree release inputs against every stable SDK and desktop tag. */
export async function checkSdkRelease(root) {
  const git = (args, options = {}) => execFileSync("git", args, {
    cwd: root, encoding: "utf8", stdio: ["pipe", "pipe", "pipe"], ...options,
  });
  if (git(["rev-parse", "--is-shallow-repository"]).trim() !== "false") {
    throw new Error("SDK release checks require complete Git history and tags (fetch-depth: 0)");
  }
  const version = versionFrom(readFileSync(join(root, versionPath), "utf8"));
  await syncSdkVersion(root, { check: true });
  if (!/^RUNTIME_API_VERSION = __version__\r?$/m.test(readFileSync(join(root, versionPath), "utf8"))) {
    throw new Error("Runtime API version must be the SDK __version__");
  }
  requireFinalizedNotes(root);

  // hash-object applies Git's clean filters (including CRLF normalization), so
  // Windows working trees compare to the same immutable blobs as Linux CI.
  const paths = [...new Set(git(["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "packages/sdk"]).split("\0"))]
    .filter((path) => contractPath(path) && existsSync(join(root, path))).sort();
  if (paths.some((path) => /[\r\n"]/.test(path))) throw new Error("Unsupported SDK source filename");
  const hashes = git(["hash-object", "--stdin-paths"], { input: `${paths.join("\n")}\n` }).trim().split("\n");
  const current = paths.map((path, index) => `${path}\0${hashes[index]}`).join("\n");
  const tags = git(["tag", "--list"]).trim().split("\n").filter((tag) => releaseTag.test(tag));
  let checked = 0;
  for (const tag of tags) {
    const ref = `refs/tags/${tag}`;
    const entries = git(["ls-tree", "-r", "-z", ref, "--", "packages/sdk"]).split("\0").filter(Boolean)
      .map((entry) => {
        const [metadata, path] = entry.split("\t");
        return { path, hash: metadata.split(" ")[2] };
      });
    // Desktop tags predating the unified SDK carry no source at this path.
    if (!entries.some(({ path }) => path === versionPath)) {
      if (tag.startsWith("sdk-v") || entries.length) throw new Error(`SDK version source missing from ${tag}`);
      continue;
    }
    const previous = versionFrom(git(["show", `${ref}:${versionPath}`]));
    if (tag.startsWith("sdk-v") && tag !== `sdk-v${previous}`) {
      throw new Error(`${tag} does not match its SDK source version ${previous}`);
    }
    if (compareVersions(version, previous) < 0) {
      throw new Error(`SDK ${version} would roll back ${previous} already distributed by ${tag}`);
    }
    if (version !== previous) continue;
    const published = entries.filter(({ path }) => contractPath(path))
      .map(({ path, hash }) => `${path}\0${hash}`).sort().join("\n");
    if (current !== published) {
      throw new Error(`SDK ${version} source differs from ${tag}; assign a new version before release`);
    }
    // Include a tag pointing to HEAD: it validates retries but cannot hide a
    // conflicting older desktop/SDK tag, since every tag is checked separately.
    checked++;
  }
  return { version, checked };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const result = await checkSdkRelease(root);
  console.log(`SDK ${result.version} finalized; ${result.checked} existing release source(s) match`);
}
